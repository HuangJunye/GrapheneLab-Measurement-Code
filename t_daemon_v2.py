

if __name__ == '__main__':

    controller = TController()
    
    while True:
        
        # read temperature from controller, update status message
        controller.read_temperature()
        controller.is_at_set()
        controller.update_status_msg()

        # print status message every minute
        update_time = datetime.now() - controller.last_status_time
        if update_time.seconds/60.0 >= controller.status_interval:
            controller.print_status_msg()
            
        # Push the reading to clients
        for j in controller.server.handlers:
            j.to_send = f'{controller.temperature:.3f} {controller.status_msg:d}'.encode()
            socket_msg = j.received_data
            if socket_msg:
                controller.read_msg(socket_msg)
        asyncore.loop(count=1, timeout=0.001)
        
        # if we are sweeping we do some things specific to the sweep
        if controller.sweep_mode:
            controller.sweep_control()

