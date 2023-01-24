import serial
import serial.tools.list_ports
import time
import json
import socket
import numpy as np
import os
import subprocess


class Labphox:

  def __init__(self, port ='', debug=False, IP=None, cmd_logging=False):
    self.debug = debug
    self.COM_port = port
    self.time_out = 20
    self.log = cmd_logging

    self.SW_version = 1
    self.communication_sleep_time = 0

    self.adc_ref = 3.3
    self.N_channel = 0
    self.board_FW = None

    if IP:
      self.USB_or_ETH = 2 # 1 for USB, 2 for ETH
    else:
      self.USB_or_ETH = 1  # 1 for USB, 2 for ETH

    self.ETH_HOST = IP # The server's IP address
    self.ETH_PORT = 7  # The port used by the server
    self.ETH_buff_size = 1024

    self.connect()

  def connect(self):
    if self.USB_or_ETH == 1:
      if self.COM_port == '':
        for device in serial.tools.list_ports.comports():
          if device.pid == 1812:
            self.PID = device.pid
            self.COM_port = device.device
            if self.debug:
              for i in device:
                print(i)

      try:
        self.serial_com = serial.Serial(self.COM_port)

        self.board_info = ''
        self.name = ''
        self.board_SN = None
        self.utility_cmd('info')
        print('Connected to ' + self.name + ' on COM port ' + self.COM_port +', PID:', str(self.PID) + ', ' +  self.board_SN +  ', channels:' + str(self.N_channel))
      except:
        print('ERROR: Couldn\'t connect')

    elif self.USB_or_ETH == 2:
      socket.setdefaulttimeout(self.time_out)

      self.board_info = ''
      self.name = ''
      self.board_SN = None
      self.utility_cmd('info')
      print('Connected to ' + self.name + ', IP:',
            str(self.ETH_HOST) + ', ' + self.board_SN + ', channels:' + str(self.N_channel))

    if self.board_FW != self.SW_version:
      raise Exception("Board Firmware version and Software version are not compatible, Board FW=" + str(self.board_FW) + " while SW=" + str(self.SW_version))

  def disconnect(self):
    self.serial_com.close()
  def input_buffer(self):
    return self.serial_com.inWaiting()

  def flush_input_buffer(self):
    return self.serial_com.flushInput()

  def write(self, cmd):
    if self.log:
      self.logging('actions', cmd)

    if self.USB_or_ETH == 1:
      self.serial_com.write(cmd)
    else:
      pass

  def read(self, size):
    if self.USB_or_ETH == 1:
      data_back = self.serial_com.read(size)
    else:
      data_back = ''

    return data_back

  def read_buffer(self):
    return self.read(self.input_buffer())

  def decode_buffer(self):
    return list(self.read_buffer())

  def debug_func(self, line):

    print('Debug:', line)


  def read_line(self):
    if self.USB_or_ETH == 1:
      return self.serial_com.readline()
    else:
      return ''

  def query_line(self, cmd):
    self.write(cmd)
    if self.USB_or_ETH == 1:
      return self.serial_com.readline()
    else:
      return ''

  def compare_cmd(self, cmd1, cmd2):
    if cmd1.upper() == cmd2.upper():
      return True
    else:
      return False

  def encode(self, value):
    return str(value).encode()

  def check_cmd_OK(self):
    if self.input_buffer():
      if 'K' in self.read(self.input_buffer()).decode().strip():
        return 'OK'

    return False

  def decode_simple_response(self, response):
    return response.decode('UTF-8').strip()

  def parse_response(self):
    ##time.sleep(1)

    reply = ''

    initial_time = time.time()
    end = False
    while not end:
      time.sleep(self.communication_sleep_time)
      if self.input_buffer():
        reply += self.read_buffer().decode()
      if ';' in reply:
        end = True

      elif (time.time() - initial_time) > self.time_out:
        raise Exception("LABPHOX time out exceeded", self.time_out, 's')


    reply = reply.split(';')[0]
    response = {'reply': reply, 'command': reply.split(':')[:-2], 'value': reply.split(':')[-1]}


    if self.log:
      self.logging('received', reply)

    return response


  def communication_handler(self, cmd, standard=True):
    response = ''
    encoded_cmd = cmd.encode()
    reply = ''

    if self.USB_or_ETH == 1:
      self.flush_input_buffer()
      self.write(encoded_cmd)


      initial_time = time.time()
      end = False
      while not end:
        time.sleep(self.communication_sleep_time)
        if self.input_buffer():
          reply += self.read_buffer().decode()
        if ';' in reply:
          end = True

        elif (time.time() - initial_time) > self.time_out:
          raise Exception("LABPHOX time out exceeded", self.time_out, 's')

      reply = reply.split(';')[0]


    elif self.USB_or_ETH == 2:
      with socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM) as s:
        s.sendto(encoded_cmd, (self.ETH_HOST, self.ETH_PORT))
        end = False
        while not end:
          time.sleep(self.communication_sleep_time)
          packet = s.recvfrom(self.ETH_buff_size)[0]
          if b';' in packet:
            reply += packet.split(b';')[0].decode()
            end = True
          else:
            try:
              reply += packet.decode()
            except:
              print('Invalid packet character', packet)
              break

        # try:
        #   reply = reply.split(';')[0]
        # except:
        #   print(reply)
        s.close()

    # if self.log:
    #   self.logging('received', response)

    try:

      if standard:
        response = {'reply': reply, 'command': reply.split(':')[:-1], 'value': reply.split(':')[-1]}
      else:
        response = reply
    except:
      print('Reply Error', reply)

    if self.debug:
      self.debug_func(response)

    return response

  def packet_handler(self, cmd, end_sequence=b'\x00\xff\x00\xff'):
    reply = b''
    encoded_cmd = cmd.encode()

    if self.USB_or_ETH == 1:
      self.flush_input_buffer()
      self.write(encoded_cmd)

      initial_time = time.time()
      end = False
      while not end:
        time.sleep(self.communication_sleep_time)
        if self.input_buffer():
          reply += self.read_buffer()
        if end_sequence in reply[-5:]:
          end = True

        elif (time.time() - initial_time) > self.time_out:
          raise Exception("LABPHOX time out exceeded", self.time_out, 's')

      reply = reply.strip(end_sequence).strip(encoded_cmd)

      return reply

    elif self.USB_or_ETH == 2:
      with socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM) as s:
        s.sendto(encoded_cmd, (self.ETH_HOST, self.ETH_PORT))
        end = False
        while not end:
          time.sleep(self.communication_sleep_time)
          packet = s.recvfrom(self.ETH_buff_size)[0]
          reply += packet.split(b';')[0]
          if end_sequence in reply[-5:]:
            end = True

        # try:
        #   reply = reply.split(';')[0]
        # except:
        #   print(reply)
        s.close()

      reply = reply.strip(end_sequence).strip(encoded_cmd)
      return reply[7:]

  def raise_value_mismatch(self):
    print('VALUE mismatch!')

  def utility_cmd(self, cmd, value=0):
    response = False
    if self.compare_cmd(cmd, 'info'):
      self.name = self.utility_cmd('name').upper()
      if 'LabP'.upper() in self.name:
        self.HW = self.utility_cmd('hw')
        self.board_SN = self.utility_cmd('sn')
        self.board_FW = int(self.utility_cmd('fw').split('.')[-1])
        self.N_channel = int(self.utility_cmd('channels').split()[1])

    elif self.compare_cmd(cmd, 'name'):
      response = self.communication_handler('W:2:A:;', standard=False)

    elif self.compare_cmd(cmd, 'fw'):
      response = self.communication_handler('W:2:B:;', standard=False)

    elif self.compare_cmd(cmd, 'hw'):
      response = self.communication_handler('W:2:D:;', standard=False)

    elif self.compare_cmd(cmd, 'sn'):
      response = self.communication_handler('W:2:E:;', standard=False)

    elif self.compare_cmd(cmd, 'channels'):
      response = self.communication_handler('W:2:F:;', standard=False)

    elif self.compare_cmd(cmd, 'connected'):
      response = self.communication_handler('W:2:C:;')
      return response['value']

    elif self.compare_cmd(cmd, 'sleep'):
      response = self.communication_handler('W:2:S:' + str(value) + ';')

    return response



  def DAC_cmd(self, cmd, DAC=1,  value=0):
    response = None
    if DAC == 1:
      sel_DAC = 5
    elif DAC == 2:
      sel_DAC = 8

    if self.compare_cmd(cmd, 'on'):
      response = self.communication_handler('W:' + str(sel_DAC) + ':T:1;')

    elif self.compare_cmd(cmd, 'off'):
      response = self.communication_handler('W:' + str(sel_DAC) + ':T:0;')

    elif self.compare_cmd(cmd, 'set'):
      response = self.communication_handler('W:' + str(sel_DAC) + ':S:' + str(value) + ';')

    elif self.compare_cmd(cmd, 'buffer'):
      response = self.communication_handler('W:' + str(sel_DAC) + ':B:' + str(value) + ';')

    return response

  def application_cmd(self, cmd, value=0):
    response = False
    if self.compare_cmd(cmd, 'pulse'):
      ##self.serial_com.flushInput()
      ##response = self.communication_handler('W:3:T:' + str(value) + ';', standard=False)
      response = self.packet_handler('W:3:T:' + str(value) + ';')
      return np.fromstring(response, dtype=np.uint8)

    elif self.compare_cmd(cmd, 'acquire'):
      response = self.communication_handler('W:3:Q:' + str(value) + ';')

    elif self.compare_cmd(cmd, 'voltage'):
      response = self.communication_handler('W:3:V:' + str(value) + ';')

    return response

  def timer_cmd(self, cmd, value=0):
    response = False
    if self.compare_cmd(cmd, 'duration'):
      response = self.communication_handler('W:0:A:' + str(value) + ';')
      if int(response['value']) != int(value):
        self.raise_value_mismatch()



    # response = self.check_cmd_OK()
    #
    # if self.debug and response:
    #   self.debug_func(response)
    #
    # if response:
    #   return response

  def ADC_cmd(self, cmd, value=0):
    response = None
    if self.compare_cmd(cmd, 'channel'):
      response = self.communication_handler('W:4:C:' + str(value) + ';')

    elif self.compare_cmd(cmd, 'start'):
      response = self.communication_handler('W:4:T:1;')

    elif self.compare_cmd(cmd, 'stop'):
      response = self.communication_handler('W:4:T:0;')

    elif self.compare_cmd(cmd, 'select'): ##Select and sample
      response = self.communication_handler('W:4:S:' + str(value) + ';')


    elif self.compare_cmd(cmd, 'get'):
      response = self.communication_handler('W:4:G:;')
      return int(response['value'])

    return response


  def gpio_cmd(self, cmd, value=0):
    response = None
    if self.compare_cmd(cmd, 'EN_3V3'):
      response = self.communication_handler('W:1:A:' + str(value) + ';')

    elif self.compare_cmd(cmd, 'EN_5V'):
      response = self.communication_handler('W:1:B:' + str(value) + ';')

    elif self.compare_cmd(cmd, 'EN_CHGP'):
      response = self.communication_handler('W:1:C:' + str(value) + ';')

    elif self.compare_cmd(cmd, 'FORCE_PWR_EN'):
      response = self.communication_handler('W:1:D:' + str(value) + ';')

    elif self.compare_cmd(cmd, 'PWR_EN'):
      response = self.communication_handler('W:1:E:' + str(value) + ';')

    elif self.compare_cmd(cmd, 'DCDC_EN'):
      response = self.communication_handler('W:1:F:' + str(value) + ';')

    elif self.compare_cmd(cmd, 'CHOPPING_EN'):
      response = self.communication_handler('W:1:G:' + str(value) + ';')

    elif self.compare_cmd(cmd, 'PWR_STATUS'):
      response = self.communication_handler('W:1:H:0;')
      return int(response['value'])

    return response

  def scanI2C(self):
    self.write(b'R:4:T:1;')
    time.sleep(5)
    res = self.read_buffer()
    print(res.decode().strip('-').split('&'))

  def IO_expander_cmd(self, cmd, port='A', value=0):
    response = None
    if self.compare_cmd(cmd, 'connect'):
      response = self.communication_handler('W:' + str(port) + ':C:' + str(value) + ';')

    elif self.compare_cmd(cmd, 'disconnect'):
      response = self.communication_handler('W:' + str(port) + ':D:' + str(value) + ';')

    elif self.compare_cmd(cmd, 'on'):
      response = self.communication_handler('W:6:O:' + str(value) + ';')

    elif self.compare_cmd(cmd, 'off'):
      response = self.communication_handler('W:6:U:' + str(value) + ';')

    elif self.compare_cmd(cmd, 'type'):
      response = self.communication_handler('W:6:S:' + str(value) + ';')

    return response


  def reset_cmd(self, cmd):
    response = None
    if self.compare_cmd(cmd, 'reset'):
      response = self.communication_handler('W:7:R:;')

    elif self.compare_cmd(cmd, 'boot'):
      response = self.communication_handler('W:7:B:;')

    return response

  def logging(self, list_name, cmd):
    with open('history.json', "r") as history_file:
      data = json.load(history_file)

    if type(cmd) == str:
      data_to_append = cmd
    elif type(cmd) == bytes:
      data_to_append = cmd.decode()

    if list_name in data.keys():
      data[list_name].append({'data': data_to_append, 'date': time.time()})
    else:
      data[list_name] = [{'data': data_to_append, 'date': time.time()}]


    with open('history.json', "w") as file:
      json.dump(data, file)




  def ETHERNET_cmd(self, cmd, value=0):
    response = None
    if self.compare_cmd(cmd, 'read'):
      response = self.communication_handler('W:Q:R:' + str(value) + ';')
    elif self.compare_cmd(cmd, 'set_ip'):
      response = self.communication_handler('W:Q:I:' + str(value) + ';')
    elif self.compare_cmd(cmd, 'get_ip'):
      response = self.communication_handler('W:Q:G:' + str(value) + ';')

    elif self.compare_cmd(cmd, 'set_ip_str'):
      int_IP = int.from_bytes(socket.inet_aton(value), "little")
      response = self.communication_handler('W:Q:I:' + str(int_IP) + ';')
    elif self.compare_cmd(cmd, 'get_ip_str'):
      response = self.communication_handler('W:Q:G:' + str(value) + ';')
      print('IP:', socket.inet_ntoa(int(response['value']).to_bytes(4, 'little')))


    return response

  def FLASH_utils(self):
    # stream = os.popen('.\dfu-util -d 0483:df11 -a 0 -s 0x08000000:leave -D .\Labphox.bin')
    # output = stream.read()
    # print(output)

    process = subprocess.Popen(['.\dfu-util', '-d 0483:df11', '-a 0', '-s 0x08000000:leave', '-D Labphox.bin'],
                               stdout=subprocess.PIPE,
                               universal_newlines=True)

    found = False
    process = subprocess.Popen(['.\dfu-util', '-l'], shell=True,
                               stdout=subprocess.PIPE,
                               universal_newlines=True)

    start_time = time.time()
    exc_time = 0
    while exc_time < self.time_out:
      output = process.stdout.readline()
      if 'Internal Flash' in output and 'Found DFU: [0483:df11]' in output:
        found = True
        break
      exc_time = time.time() - start_time

    if not found:
      print('Couldn\'t find the the device')
    else:
      print('Device found in', output.strip().strip('Found DFU: '))

      process = subprocess.Popen('.\dfu-util -d 0483:df11 -a 0 -s 0x08000000:leave -D .\Labphox.bin', shell=True,
                                 stdout=subprocess.PIPE,
                                 universal_newlines=True)

      start_time = time.time()
      exc_time = 0
      poll = process.poll()
      while poll is None:
        output = process.stdout.readline()
        if 'Download' in output or 'device'.upper() in output.upper() or 'dfu'.upper() in output.upper() and 'bugs' not in output:
          print(output.strip())
        exc_time = time.time() - start_time

        if exc_time > 40:
          break
        else:
          poll = process.poll()

      print('Flashing time', exc_time)





if __name__ == "__main__":

  cryoswitch = Labphox(IP='192.168.1.6')
  cryoswitch.application_cmd('pulse')
  cryoswitch.scanI2C()


