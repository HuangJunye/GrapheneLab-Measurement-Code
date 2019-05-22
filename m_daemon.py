import asyncore
import time
from datetime import datetime

from daemon.MControl import MControl
		

if __name__ == '__main__':
	
	# Initialize a daemon instance and runs startup codes
	control = MControl()
	control.magnet_on_start_up()
	# A flag to control the source behavior
	source_flag = False
	
	while 1:
		
		# Read the field and update the ready message
		control.magnet_read_field()

		# Push the reading to clients
		for j in control.server.handlers:
			j.to_send = f",{control.field:.5f} {control.ready:d}".encode()
			socket_msg = j.received_data
			if socket_msg and socket_msg != "-":
				control.read_msg(socket_msg)
		asyncore.loop(count=1, timeout=0.001)
				
		""" Now we should do stuff depending on the socket and what we 
		were doing before reading the socket
		In order of precedence
		1. We are locked, waiting for the switch heater -> delay any actions
		2. Go to the target field
		3. Go to the target heater
		4. ... just chill out! 
		"""
		
		if control.lock:
			# Check if we can release the lock
			wait = datetime.now() - control.lock_time
			if wait.seconds >= 120.0:
				# Unlock
				control.lock = False
				print("Unlocking...")

		if not control.lock and not control.ready:
			""" The magnet is not locked and not ready
			We now try to go to the target_field and
			set the target_heater 
			"""
			
			if not control.query_at_target():
				# System is not at the target field
				if not control.heater:
					# The heater is not on
					if control.magnet_check_switchable():
						# The switch heater can be switched ON --> so switch it ON
						control.magnet_set_heater(True) 
						# this will set the lock so we need to get out of the loop without doing anything else
					else:
						# The switch heater is not on
						action = control.magnet_read_action()
						if action != "RTOS":
							# The source is not ramping --> Ramp it to the magnet current so it can be switched
							control.set_source(control.magnet_current)
				else:
					# The heater is on --> so go to the target
					action = control.magnet_read_action()
					set_current = control.magnet_read_numeric("CSET")
					if action != "RTOS" or abs(set_current - control.target_field * control.a_to_b) > 0.005:
						# The source is not ramping --> Ramp it to the magnet current so it can be switched
						target_current = control.target_field * control.a_to_b
						control.set_source(target_current)
			
			elif control.heater != control.target_heater:
				""" The magnet is at the target field but the heater is not in the target state
				There are two possibilities
				1. The heater is now ON --> turn it off and ramp the source down
				2. The heater is OFF --> Set the source to magnet current and turn it on 
				"""
				if control.heater:
					# The heater is on
					if control.magnet_check_switchable():
						control.magnet_set_heater(False)
						# Set the source flag to tell the source to ramp to zero
						source_flag = True

				else:
					# The heater is not on
					if control.magnet_check_switchable():
						# The switch heater can be switched ON --> so switch it ON
						control.magnet_set_heater(True)
						# this will set the lock so we need to get out of the loop without doing anything else
					else:
						# The switch heater is not on
						action = control.magnet_read_action()
						if action != "RTOS":
							# The source is not ramping --> Ramp it to the magnet current so it can be switched
							control.set_source(control.magnet_current)

		if not control.lock and source_flag:
			# The source_flag has been set ramp the source to zero and unset the flag
			control.magnet_set_action("RTOZ")
			source_flag = False
			
		time.sleep(0.4)
