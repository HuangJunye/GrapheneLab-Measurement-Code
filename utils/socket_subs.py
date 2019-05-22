


"""Sub programs for operation of the PicoWatt and Leiden TCS to control temperature

author : Eoin O'Farrell
email : phyoec@nus.edu.sg
last edited : August 2013

This file contains some utilities to create a socket server, handler and client

"""

import asyncore
import socket
import logging
logging.basicConfig(filename='server_debug.log', level=logging.DEBUG)


class SockServer(asyncore.dispatcher):

	def __init__(self, address):
		self.logger = logging.getLogger('EchoServer')
		asyncore.dispatcher.__init__(self)
		self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
		self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.bind(address)
		self.address = self.socket.getsockname()
		self.logger.debug('binding to %s', self.address)
		self.listen(1)
		self.handlers = []
		return

	def handle_accept(self):
		# Called when a client connects to our socket
		client_info = self.accept()
		self.logger.debug('handle_accept() -> %s', client_info[1])
		handler = SockHandler(client_info[0], self)
		print("Got listener!")
		if len(self.handlers) > 2:
			self.remove_channel(self.handlers[-1])
		self.handlers.append(handler)
		return

	def remove_channel(self, sock):
		if sock in self.handlers:
			self.handlers.remove(sock)
			print("Listener disconnect!")

	def handle_close(self):
		self.logger.debug('handle_close()')
		self.close()
		return


class SockHandler(asyncore.dispatcher):

	def __init__(self, sock, server, chunk_size=256):
		self.chunk_size = chunk_size
		self.logger = logging.getLogger('EchoHandler%s' % str(sock.getsockname()))
		asyncore.dispatcher.__init__(self, sock=sock)
		self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.to_send = ""
		self.received_data = ""
		self.server = server
		return

	def writable(self):
		self.logger.debug('writable() -> %s', bool(self.to_send))
		return bool(self.to_send)

	def handle_write(self):
		if len(self.to_send) > self.chunk_size:
			# if the buffer is too long bin some
			sent = self.send(self.to_send[-self.chunk_size:])	
			self.to_send = ""
		else:
			sent = self.send(self.to_send[:self.chunk_size])
			self.to_send = self.to_send[sent:]

	def handle_read(self):
		data = self.recv(self.chunk_size)
		self.logger.debug('handle_read() -> (%d) "%s"', len(data), data)
		self.received_data = data

	def handle_close(self):
		self.logger.debug('handle_close()')
		self.server.remove_channel(self)
		self.close()


class SockClient(asyncore.dispatcher):

	def __init__(self, host, port, chunk_size=256):
		# self.message = message
		self.to_send = ""
		self.received_data = ""
		self.chunk_size = chunk_size
		self.logger = logging.getLogger('EchoClient')
		asyncore.dispatcher.__init__(self)
		self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
		self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.logger.debug('connecting to %s', (host, port))
		self.connect((host, port))
		return

	def handle_close(self):
		self.logger.debug('handle_close()')
		self.close()
		pass

	def writable(self):
		self.logger.debug('writable() -> %s', bool(self.to_send))
		return bool(self.to_send)

	def handle_write(self):
		if len(self.to_send) > self.chunk_size:
			# if the buffer is too long bin some
			sent = self.send(self.to_send[-self.chunk_size:])	
			self.to_send = ""
		else:
			sent = self.send(self.to_send[:self.chunk_size])
			self.to_send = self.to_send[sent:]
		self.logger.debug('handle_write() -> (%d) "%s"', sent, self.to_send[:sent])

	def handle_read(self):
		data = self.recv(self.chunk_size)
		self.logger.debug('handle_read() -> (%d) "%s"', len(data), data)
		self.received_data = data
