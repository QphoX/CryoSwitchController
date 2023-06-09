import time
import matplotlib.pyplot as plt
from libphox import Labphox
import numpy as np
import json
import os

class Cryoswitch:

    def __init__(self, debug=False, COM_port='', IP=None, SN=None):
        self.debug = debug
        self.port = COM_port
        self.IP = IP
        self.verbose = True

        self.labphox = Labphox(self.port, debug=self.debug, IP=self.IP, SN=SN)
        self.ports_enabled = self.labphox.N_channel
        self.SN = self.labphox.board_SN
        self.HW_rev = self.get_HW_revision()

        self.wait_time = 0.1
        self.pulse_duration_ms = 15
        self.converter_voltage = 5
        self.MEASURED_converter_voltage = 0
        self.current_switch_model = ''

        self.abs_path = os.path.dirname(__file__) + '\\'

        self.decimals = 2
        self.plot = True
        self.log_wav = True
        self.log_wav_dir = self.abs_path + r'data'
        self.align_edges = True

        self.pulse_logging = True
        self.pulse_logging_filename = self.abs_path + r'pulse_logging.txt'
        self.log_pulses_to_display = 5
        self.warning_threshold_current = 60

        self.track_states = True
        self.track_states_file = self.abs_path + r'states.json'

        self.constants_file_name = self.abs_path + r'constants.json'
        self.__constants()

        if self.track_states:
            self.tracking_init()

        if self.pulse_logging:
            self.pulse_logging_init()

        if self.log_wav:
            self.log_wav_init()

    def tracking_init(self):
        file = open(self.track_states_file)
        states = json.load(file)
        file.close()
        if self.SN not in states.keys():
            states[self.SN] = states['SN']
            with open(self.track_states_file, 'w') as outfile:
                json.dump(states, outfile, indent=4, sort_keys=True)

    def pulse_logging_init(self):
        if not os.path.isfile(self.pulse_logging_filename):
            file = open(self.pulse_logging_filename, 'w')
            file.close()

    def log_wav_init(self):
        if not os.path.isdir(self.log_wav_dir):
            os.mkdir(self.log_wav_dir)

    def __constants(self):
        file = open(self.constants_file_name)
        constants = json.load(file)[self.HW_rev]
        file.close()

        self.ADC_12B_res = constants['ADC_12B_res']
        self.ADC_8B_res = constants['ADC_8B_res']

        self.bv_R1 = constants['bv_R1']
        self.bv_R2 = constants['bv_R2']
        self.bv_ADC = constants['bv_ADC']

        self.converter_divider = constants['converter_divider']
        self.converter_ADC = constants['converter_ADC']

        self.converter_VREF = constants['converter_VREF']
        self.converter_R1 = constants['converter_R1']
        self.converter_R2 = constants['converter_R2']
        self.converter_Rf = constants['converter_Rf']
        self.converter_DAC_lower_bound = constants['converter_DAC_lower_bound']
        self.converter_DAC_upper_bound = constants['converter_DAC_upper_bound']

        self.OCP_gain = constants['OCP_gain']

        self.current_sense_R = constants['current_sense_R']
        self.current_gain = constants['current_gain']

        self.sampling_freq = 28000
        self.temperature_ADC = 16

        if self.HW_rev == 'HW_Ver. 3':
            ref_values = []
            for it in range(5):
                ref_values.append(self.get_V_ref())
            self.measured_adc_ref = sum(ref_values) / len(ref_values)
        else:
            self.measured_adc_ref = self.labphox.adc_ref

    def set_FW_upgrade_mode(self):
        self.labphox.reset_cmd('boot')

    def flash(self, path=None):
        reply = input('Are you sure you want to flash the device?')
        if 'Y' in reply.upper():
            self.set_FW_upgrade_mode()
            time.sleep(5)
            self.labphox.FLASH_utils(path)
        else:
            print('Aborting flash sequence...')

    def reset(self):
        self.labphox.reset_cmd('reset')
        time.sleep(3)

    def reconnect(self):
        self.labphox.connect()

    def enable_5V(self):
        self.labphox.gpio_cmd('EN_5V', 1)

    def disable_5V(self):
        self.labphox.gpio_cmd('EN_5V', 0)

    def enable_3V3(self):
        self.labphox.gpio_cmd('EN_3V3', 1)

    def disable_3V3(self):
        self.labphox.gpio_cmd('EN_3V3', 0)

    def get_internal_temperature(self):
        self.labphox.ADC_cmd('select', self.temperature_ADC)
        time.sleep(0.5)
        V_temp = self.labphox.ADC_cmd('get') * self.measured_adc_ref / self.ADC_12B_res
        temperature = round(((V_temp - 0.76) / 0.0025) + 25, self.decimals)
        return temperature

    def get_converter_voltage(self):
        converter_gain = self.measured_adc_ref * self.converter_divider / self.ADC_12B_res
        self.labphox.ADC_cmd('select', self.converter_ADC)
        converter_voltage = round(self.labphox.ADC_cmd('get') * converter_gain, self.decimals)
        self.MEASURED_converter_voltage = converter_voltage
        return converter_voltage

    def get_bias_voltage(self):
        bias_gain = self.measured_adc_ref * ((self.bv_R2 + self.bv_R1) / self.bv_R1) / self.ADC_12B_res
        bias_offset = self.measured_adc_ref*self.bv_R2/self.bv_R1

        self.labphox.ADC_cmd('select', self.bv_ADC)
        time.sleep(self.wait_time)
        bias_voltage = self.labphox.ADC_cmd('get')*bias_gain-bias_offset

        return bias_voltage

    def check_voltage(self, measured_voltage, target_voltage, tolerance=0.1, pre_str=''):
        error = abs((measured_voltage-target_voltage)/target_voltage)
        if error > tolerance:
            print(pre_str, 'failed to set voltage, measured voltage', round(measured_voltage, self.decimals))
            return False
        else:
            print(pre_str, 'voltage set to', round(measured_voltage, self.decimals), 'V')
            return True

    def get_HW_revision(self):
        return self.labphox.HW

    def enable_negative_supply(self):
        self.labphox.gpio_cmd('EN_CHGP', 1)
        time.sleep(2)
        bias_voltage = self.get_bias_voltage()
        if self.verbose:
            self.check_voltage(bias_voltage, -5, tolerance=0.1, pre_str='BIAS STATUS:')
        return bias_voltage

    def disable_negative_supply(self):
        self.labphox.gpio_cmd('EN_CHGP', 0)
        return self.get_bias_voltage()

    def calculate_output_code(self, Vout):
        code = int((self.converter_VREF - (
                    Vout - self.converter_VREF * (1 + (self.converter_R1 / self.converter_R2))) * (
                                self.converter_Rf / self.converter_R1)) * (self.ADC_12B_res / self.measured_adc_ref))

        if code < self.converter_DAC_lower_bound or code > self.converter_DAC_upper_bound:
            print('Wrong DAC value, dont mess with the DAC. DAC angry.')
            return False

        return code

    def set_output_voltage(self, Vout):
        if 5 <= Vout <= 30:
            self.converter_voltage = Vout
            if Vout > 10:
                self.disable_negative_supply()
            else:
                self.enable_negative_supply()

            self.labphox.DAC_cmd('on', DAC=1)
            code = self.calculate_output_code(Vout)

            if code:
                self.labphox.DAC_cmd('set', DAC=1, value=code)

                time.sleep(1)
                measured_voltage = self.get_converter_voltage()
                tolerance = 0.1
                if self.verbose:
                    self.check_voltage(measured_voltage, Vout, tolerance=tolerance, pre_str='CONVERTER STATUS:')

                return measured_voltage
        else:
            print('Voltage outside of range (5-28V)')

        return False

    def enable_output_channels(self):
        enabled = False
        counter = 0
        response = {}
        while not enabled:
            response = self.labphox.IO_expander_cmd('on')
            if int(response['value']) == 0:
                enabled = True
            elif counter > 3:
                break
            counter += 1

        if not int(response['value']) == 0:
            print('Failed to enable output channels!', str(response['value']))
        elif self.verbose and counter > 1:
            print(counter, 'attempts to enable output channel')

        return int(response['value'])

    def disable_output_channels(self):
        self.labphox.IO_expander_cmd('off')

    def enable_converter(self, init_voltage=None):
        self.labphox.DAC_cmd('set', DAC=1, value=1500)
        self.labphox.DAC_cmd('on', DAC=1)
        self.labphox.gpio_cmd('PWR_EN', 1)
        self.labphox.gpio_cmd('DCDC_EN', 1)

        if init_voltage is None:
            init_voltage = self.converter_voltage

        self.set_output_voltage(init_voltage)


    def disable_converter(self):
        self.labphox.gpio_cmd('DCDC_EN', 0)
        self.labphox.DAC_cmd('set', DAC=1, value=1500)

        self.labphox.gpio_cmd('PWR_EN', 0)

    def enable_OCP(self):
        self.labphox.DAC_cmd('set', DAC=2, value=1500)

        self.labphox.DAC_cmd('on', DAC=2)
        self.set_OCP_mA(100)

    def reset_OCP(self):
        self.labphox.gpio_cmd('CHOPPING_EN', 1)
        self.labphox.gpio_cmd('CHOPPING_EN', 0)

    def set_OCP_mA(self, value):
        DAC_reg = int(value*(self.current_sense_R*self.current_gain*self.ADC_12B_res/(self.OCP_gain*1000*self.measured_adc_ref)))

        if 0 < DAC_reg < 4095:
            self.labphox.DAC_cmd('set', DAC=2, value=DAC_reg)
        else:
            print('Over current protection outside of range')

    def get_OCP_status(self):
        return self.labphox.gpio_cmd('OCP_OUT_STATUS')

    def enable_chopping(self):
        self.labphox.gpio_cmd('CHOPPING_EN', 1)

    def disable_chopping(self):
        self.labphox.gpio_cmd('CHOPPING_EN', 0)

    def reset_output_supervisor(self):
        self.disable_converter()
        self.labphox.gpio_cmd('FORCE_PWR_EN', 1)
        time.sleep(0.5)
        self.labphox.gpio_cmd('FORCE_PWR_EN', 0)
        self.enable_converter()

    def get_output_state(self):
        return self.labphox.gpio_cmd('PWR_STATUS')

    def set_pulse_duration_ms(self, ms_duration):
        if ms_duration <= 100:
            self.pulse_duration_ms = ms_duration
            pulse_offset = 100
            self.labphox.timer_cmd('duration', round(ms_duration*100 + pulse_offset))
            if self.verbose:
                print('Pulse duration set to', str(ms_duration) + 'ms')

        else:
            print('Pulse duration outside of range (1-100ms)')

    def set_sampling_frequency_khz(self, f_khz):
        if 10 <= f_khz <= 100:
            self.labphox.timer_cmd('sampling', int(84000/f_khz))
            self.sampling_freq = f_khz*1000
        else:
            print('Sampling frequency outside of range')

    def send_pulse(self):
        if not self.get_power_status():
            print('WARNING: Timing protection triggered, resetting...')
            self.reset_output_supervisor()

        current_gain = 1000 * self.measured_adc_ref / (self.current_sense_R * self.current_gain * self.ADC_8B_res)

        current_data = self.labphox.application_cmd('pulse', 1)

        return current_data*current_gain


    def select_switch_model(self, model='R583423141'):
        if model.upper() == 'R583423141'.upper():
            self.current_switch_model = 'R583423141'
            self.labphox.IO_expander_cmd('type', value=1)
            return True

        elif model.upper() == 'R573423600'.upper():
            self.current_switch_model = 'R573423600'
            self.labphox.IO_expander_cmd('type', value=2)
            return True
        else:
            return False

    def validate_selected_channel(self, number, polarity, reply):
        if polarity and self.current_switch_model == 'R583423141':
            shift_byte = 0b0110
            offset = 0
        elif not polarity and self.current_switch_model == 'R583423141':
            shift_byte = 0b1001
            offset = 0
        elif polarity and self.current_switch_model == 'R573423600':
            shift_byte = 0b10
            offset = 4096
        elif not polarity and self.current_switch_model == 'R573423600':
            shift_byte = 0b01
            offset = 8192
        else:
            shift_byte = 0
            offset = 0

        validation_id = (shift_byte << 2 * number) + offset
        validation_id1 = validation_id & 255
        validation_id2 = validation_id >> 8

        if int(reply['value']) != validation_id1|validation_id2:
            print('Wrong channel validation ID')
            print('Validation ID, Received', reply['value'], '->Expected', validation_id1 | validation_id2)
            return False
        else:
            return True


    def select_output_channel(self, port, number, polarity):
        if 0 < number < 7:
            number = number - 1
            if polarity:
                reply = self.labphox.IO_expander_cmd('connect', port, number)
            else:
                reply = self.labphox.IO_expander_cmd('disconnect', port, number)

            return self.validate_selected_channel(number, polarity, reply)
        else:
            print('SW out of range')
            return None

    def select_and_pulse(self, port, contact, polarity):
        if self.track_states:
            self.save_switch_state(port, contact, polarity)

        if polarity:
            polarity = 1
            polarity_str = 'Connect'
        else:
            polarity = 0
            polarity_str = 'Disconnect'

        selection_result = self.select_output_channel(port, contact, polarity)

        if selection_result:
            current_profile = self.send_pulse()
            self.disable_output_channels()

            if self.plot:
                sampling_period = 1 / self.sampling_freq

                if self.align_edges:
                    edge = np.argmax(current_profile>0)
                    current_data = current_profile[edge:]
                else:
                    current_data = current_profile
                data_points = len(current_data)
                x_axis = np.linspace(0, data_points*sampling_period, data_points)*1000
                plt.plot(x_axis, current_data)
                plt.xlabel('Time [ms]')
                plt.ylabel('Current [mA]')
                plt.title(time.strftime("%b-%m %H:%M:%S%p", time.gmtime()))
                plt.suptitle('Port ' + port + '-' + str(contact) + ' ' + polarity_str)


                if self.current_switch_model == 'R583423141':
                    plt.ylim(0, 100)
                elif self.current_switch_model == 'R573423600':
                    plt.ylim(0, 200)
                plt.grid()
                plt.show()

            if self.pulse_logging:
                self.log_pulse(port, contact, polarity, current_profile.max())
            if self.log_wav:
                self.log_waveform(port, contact, polarity, current_profile)
            return current_profile

        else:
            return []

    def save_switch_state(self, port, contact, polarity):
        file = open(self.track_states_file)
        states = json.load(file)
        file.close()

        SN = self.SN
        port = 'port_' + str(port)
        contact = 'contact_' + str(contact)
        if SN in states.keys():
            states[SN][port][contact] = polarity

            with open(self.track_states_file, 'w') as outfile:
                json.dump(states, outfile, indent=4, sort_keys=True)

    def get_switches_state(self, port=None):
        file = open(self.track_states_file)
        states = json.load(file)
        file.close()
        ports = []
        if self.ports_enabled == 1:
            ports = ['A']
        elif self.ports_enabled == 2:
            ports = ['A', 'B']
        elif self.ports_enabled == 3:
            ports = ['A', 'B', 'C']
        elif self.ports_enabled == 4:
            ports = ['A', 'B', 'C', 'D']

        if self.SN in states.keys():
            if port in ports:
                current_state = states[self.SN]
                print('Port ' + port + ' state')
                for switch in range(1, 7):
                    state = current_state['port_' + port]['contact_' + str(switch)]
                    if state:
                        if switch == 1:
                            print(str(switch) + ' ----' + chr(0x2510))
                        else:
                            print(str(switch) + ' ----' + chr(0x2524))
                    else:
                        print(str(switch) + ' -  -' + chr(0x2502))
                print('      ' + chr(0x2514) + '- COM')
                print('')

            return states[self.SN]
        else:
            return None


    def log_waveform(self, port, contact, polarity, current_profile):
        name = self.log_wav_dir + '\\' + str(int(time.time())) + '_' + str(
            self.MEASURED_converter_voltage) + 'V_' + str(port) + str(contact) + '_' + str(polarity) + '.json'
        waveform = {'time':time.time(), 'voltage': self.MEASURED_converter_voltage, 'port': port, 'contact': contact, 'polarity':polarity, 'SF': self.sampling_freq, 'data': list(current_profile)}
        with open(name, 'w') as outfile:
            json.dump(waveform, outfile, indent=4, sort_keys=True)


    def log_pulse(self, port, contact, polarity, max_current):
        if polarity:
            direction = 'Connect   '
        else:
            direction = 'Disconnect'

        pulse_string = direction + '-> Port:' + port + '-' + str(contact) + ', CurrentMax:' + str(round(max_current)) + ' Timestamp:' + str(int(time.time()))

        if max_current < self.warning_threshold_current:
            warning_string = ' *Warnings: Low current detected!'
        else:
            warning_string = ''

        with open(self.pulse_logging_filename, 'a') as logging_file:
            logging_file.write(pulse_string + warning_string + '\n')

    def get_pulse_history(self, port=None, pulse_number=None):
        if not pulse_number:
            pulse_number = self.log_pulses_to_display

        with open(self.pulse_logging_filename, 'r') as logging_file:
            pulse_info = logging_file.readlines()

        list_for_display = []
        counter = 0
        for idx, pulse in enumerate(pulse_info):
            pulse = pulse_info[-idx-1]
            if port:
                if "Port:" + port + "-" in pulse:
                    list_for_display.append(pulse)
                    counter += 1
            else:
                list_for_display.append(pulse)
                counter += 1

            if counter >= pulse_number:
                break

        for idx, pulse in enumerate(list_for_display):
            raw_data = list_for_display[-idx - 1].split(',')
            if '*' in raw_data[-1]:
                extra_text = raw_data[1].split('*')[-1].strip()
                pulse_time = time.localtime(int(raw_data[1].split('*')[0].split(':')[-1].strip()))
            else:
                extra_text = ''
                pulse_time = time.localtime(int(raw_data[1].split(':')[-1].strip()))

            print(raw_data[0] + ', ' + time.strftime("%a %b-%m %H:%M:%S%p", pulse_time) + ' ' + extra_text)

    def connect(self, port, contact):
        if port == 'A' and self.ports_enabled >= 1:
            send_pulse = True
        elif port == 'B' and self.ports_enabled >= 2:
            send_pulse = True
        elif port == 'C' and self.ports_enabled >= 3:
            send_pulse = True
        elif port == 'D' and self.ports_enabled >= 4:
            send_pulse = True
        else:
            print('Port', port, 'not enabled')
            return None

        if send_pulse and (0 < contact < 7):
            if self.debug:
                print('Connecting port:', port, 'SW:', contact)

            current_profile = self.select_and_pulse(port, contact, 1)
            return current_profile
        else:
            print('Out of range: Port', port)
            return None

    def disconnect(self, port, contact):
        if port == 'A' and self.ports_enabled >= 1:
            send_pulse = True
        elif port == 'B' and self.ports_enabled >= 2:
            send_pulse = True
        elif port == 'C' and self.ports_enabled >= 3:
            send_pulse = True
        elif port == 'D' and self.ports_enabled >= 4:
            send_pulse = True
        else:
            print('Port', port, 'not enabled')
            return None

        if send_pulse and (0 < contact < 7):
            if self.debug:
                print('Disconnecting port:', port, 'SW:', contact)

            current_profile = self.select_and_pulse(port, contact, 0)
            return current_profile
        else:
            print('Out of range: Port', port)

    def disconnect_all(self, port):
        for contact in range(1, 7):
            self.disconnect(port, contact)

    def smart_connect(self, port, contact, force=False):
        states = self.get_switches_state()
        port_state = states['port_' + port]
        contacts = [1, 2, 3, 4, 5, 6]
        contacts.remove(contact)
        for other_contact in contacts:
            if port_state['contact_' + str(other_contact)] == 1:
                print('Disconnecting', other_contact)
                self.disconnect(port, other_contact)

        if port_state['contact_' + str(contact)] == 1:
            print('Contact', contact, 'is already connected')
            if force:
                print('Connecting', contact)
                return self.connect(port, contact)
        else:
            print('Connecting', contact)
            return self.connect(port, contact)

        return None

    def get_power_status(self):
        return self.labphox.gpio_cmd('PWR_STATUS')

    def set_ip(self, add='192.168.1.101'):
        self.labphox.ETHERNET_cmd('set_ip_str', add)

    def get_ip(self):
        add = self.labphox.ETHERNET_cmd('get_ip_str')
        print('IP:', add)
        return add

    def set_sub_net_mask(self, mask='255.255.255.0'):
        self.labphox.ETHERNET_cmd('set_mask_str', mask)

    def get_sub_net_mask(self):
        mask = self.labphox.ETHERNET_cmd('get_mask_str')
        print('Subnet Mask:', mask)
        return mask

    def get_V_ref(self):
        self.labphox.ADC3_cmd('select', 8)
        time.sleep(0.2)
        Ref_2V5 = self.labphox.ADC3_cmd('get')
        ADC_ref = 2.5*4095/Ref_2V5
        return round(ADC_ref, 4)

    def start(self):
        if self.verbose:
            print('Initialization...')
        self.labphox.ADC_cmd('start')
        if '3' in self.HW_rev:
            self.labphox.ADC3_cmd('start')

        self.enable_3V3()
        self.enable_5V()
        self.enable_OCP()
        self.set_OCP_mA(80)
        self.enable_chopping()

        self.set_pulse_duration_ms(15)

        self.enable_converter()
        # self.set_output_voltage(5)

        time.sleep(1)
        self.enable_output_channels()
        self.select_switch_model('R583423141')

        if not self.get_power_status():
            if self.verbose:
                print('POWER STATUS: Output voltage not enabled')
        else:
            if self.verbose:
                print('POWER STATUS: Ready')


if __name__ == "__main__":
    switch = Cryoswitch(IP='192.168.1.101') ## -> CryoSwitch class declaration and USB connection

    switch.start() ## -> Initialization of the internal hardware

    switch.get_pulse_history(pulse_number=5, port='A') ##-> Show the last 5 pulses send through on port A
    switch.set_output_voltage(5) ## -> Set the output pulse voltage to 5V

    switch.connect(port='A', contact=1) ## Connect contact 1 of port A to the common terminal
    switch.disconnect(port='A', contact=1) ## Disconnects contact 1 of port A from the common terminal
    switch.smart_connect(port='A', contact=1) ## Connect contact 1 and disconnect wichever port was connected previously (based on the history)




