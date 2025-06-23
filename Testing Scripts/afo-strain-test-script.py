import csv
import time
from threading import Thread
from Phidget22.Phidget import *
from Phidget22.Devices.VoltageRatioInput import *
import odrive
from odrive.enums import *

# Phidget calibration parameters
gain = -8133.8  # Example value
offset = 0
newton_to_grams = 1000
calibrated = False

# CSV file for logging
csv_filename = "combined_log-(5-deg-sec)-no-afo.csv"

# ODrive setup
odrive_serial_number = "3943355F3231"

# Data buffer for logging
data_buffer = []
logging_active = True

# Initialize CSV file with headers
with open(csv_filename, mode="w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow([
        "Timestamp", "Weight (grams)",
        "Cycle", "AFO Angle (Degrees)", "Velocity (turns/s)", "Position (degrees)"
    ])

# Logger class
class Logger:
    def __init__(self, odrive_device, voltage_ratio_input):
        self.odrive_device = odrive_device
        self.voltage_ratio_input = voltage_ratio_input
        self.cycle = 0

    def log_data(self, voltage_ratio):
        global calibrated, offset, data_buffer

        if calibrated:
            weight_newtons = (voltage_ratio - offset) * gain
            weight_grams = weight_newtons * newton_to_grams
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

            position = self.odrive_device.axis0.pos_vel_mapper.pos_rel * 17.3  # Convert to degrees
            velocity = self.odrive_device.axis0.pos_vel_mapper.vel

            # Add data row to buffer
            data_buffer.append([
                timestamp, weight_grams, self.cycle, position, velocity
            ])

            # Print for reference
            print(
                f"Timestamp: {timestamp}, Weight: {weight_grams} g, "
                f"Cycle: {self.cycle}, Position: {position} degrees, "
                f"Velocity: {velocity} turns/s"
            )
        else:
            print("Phidget is not calibrated yet!")

# Tare function
def tare_scale(voltage_ratio_input):
    global offset, calibrated
    num_samples = 16

    for _ in range(num_samples):
        offset += voltage_ratio_input.getVoltageRatio()
        time.sleep(voltage_ratio_input.getDataInterval() / 1000.0)

    offset /= num_samples
    print(f"Tare offset: {offset}")
    calibrated = True

# Continuous voltage ratio updates in a thread
def update_voltage_ratio(logger):
    global logging_active
    while logging_active:
        voltage_ratio = logger.voltage_ratio_input.getVoltageRatio()
        logger.log_data(voltage_ratio)
        time.sleep(0.001)  # 1 ms delay for high-frequency updates

# Motor control and logging
def motor_control_and_log(num_cycles, velocity, logger, odrive_zero):
    global logging_active

    try:
        logger.odrive_device.axis0.controller.config.control_mode = CONTROL_MODE_POSITION_CONTROL
        logger.odrive_device.axis0.controller.config.input_mode = INPUT_MODE_TRAP_TRAJ
        logger.odrive_device.axis0.trap_traj.config.vel_limit = 1000
        logger.odrive_device.axis0.trap_traj.config.accel_limit = 30
        logger.odrive_device.axis0.trap_traj.config.decel_limit = 30

        logger.odrive_device.axis0.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
        time.sleep(0.1)

        angle_limits = [-4, 4]
        for deg_sec in velocity:
            print(f"Starting cyclic test at {deg_sec} Hz")
            logger.odrive_device.axis0.controller.config.vel_limit = deg_sec

            for cycle in range(1, num_cycles + 1):
                logger.cycle = cycle
                print(f"Cycle {cycle} of {num_cycles}")

                # Move to minimum angle limit
                logger.odrive_device.axis0.controller.input_pos = angle_limits[0] / 17.3
                while abs(logger.odrive_device.axis0.pos_vel_mapper.pos_rel - ((angle_limits[0] / 17.3))+abs(odrive_zero)) > 0.01 + abs(odrive_zero):
                    pass

                # Move to maximum angle limit
                logger.odrive_device.axis0.controller.input_pos = angle_limits[1] / 17.3
                while abs(logger.odrive_device.axis0.pos_vel_mapper.pos_rel - ((angle_limits[1] / 17.3))+abs(odrive_zero)) > 0.01 + abs(odrive_zero):
                    pass

        logger.odrive_device.axis0.controller.input_pos = 0
        while abs(logger.odrive_device.axis0.pos_vel_mapper.pos_rel - 0) > 0.01:
            pass

        logger.odrive_device.axis0.requested_state = AXIS_STATE_IDLE
        print("Motor test completed.")

        # Write all buffered data to the CSV file
        with open(csv_filename, mode="a", newline="") as file:
            writer = csv.writer(file)
            writer.writerows(data_buffer)
        print(f"Data written to {csv_filename}")

    except Exception as e:
        print(f"Motor control error: {e}")
    finally:
        logging_active = False

# Main function
def main():
    global calibrated, logging_active

    try:
        # Find ODrive
        odrive_device = odrive.find_any(serial_number=odrive_serial_number)
        odrive_device.clear_errors()
        print(f"Connected to ODrive with serial {odrive_serial_number}")

        # Initialize Phidget
        voltage_ratio_input = VoltageRatioInput()
        voltage_ratio_input.setChannel(1)
        voltage_ratio_input.openWaitForAttachment(5000)
        voltage_ratio_input.setDataInterval(8)  # Set minimum interval for max update rate

        # Create logger instance
        logger = Logger(odrive_device, voltage_ratio_input)

        print("Taring scale...")
        tare_scale(voltage_ratio_input)
        print("Scale tared.")

        # Get user input
        cycles_input = input("How many cycles do you want to perform? ")
        if cycles_input.isdigit():
            num_cycles = int(cycles_input)
            # Start the thread for continuous voltage ratio updates
            update_thread = Thread(target=update_voltage_ratio, args=(logger,))
            update_thread.start()
        else:
            print("Invalid number of cycles.")
            return

        # Convert to counts per second
        odrive_speed = 5

        velocity = [(odrive_speed*10 / 360)*2]
        odrive_zero = odrive_device.axis0.controller.input_pos

        motor_control_and_log(num_cycles, velocity, logger, odrive_zero)

        input("Press Enter to stop logging...\n")
        voltage_ratio_input.close()
        logging_active = False
        update_thread.join()
        print("Program terminated.")

    except (Exception, KeyboardInterrupt) as e:
        logging_active = False
        print(f"Program terminated due to error or user interruption: {e}")

if __name__ == "__main__":
    main()




















# import csv
# import time
# import threading
# from Phidget22.Phidget import *
# from Phidget22.Devices.VoltageRatioInput import *
# import odrive
# from odrive.enums import *
# import openpyxl

# # Phidget calibration parameters
# gain = -8133.8  # Example value
# offset = 0
# newton_to_grams = 1000
# calibrated = False

# # CSV file for weight logging
# csv_filename = "weight_log.csv"

# # Excel file for motor logging
# excel_filename = "Motor_Angle_Cyclic_Test.xlsx"

# # ODrive setup
# odrive_serial_number = "3943355F3231"


# # Initialize weight CSV
# with open(csv_filename, mode="w", newline="") as file:
#     writer = csv.writer(file)
#     writer.writerow(["Timestamp", "Weight (grams)"])

# # Initialize Excel workbook for motor logging
# workbook = openpyxl.Workbook()
# worksheet = workbook.active
# worksheet.title = "Test Data"
# worksheet.append(["Timestamp (s)", "Cycle", "AFO Position (Degrees)", "Velocity (turns/s)"])

# # Phidget callback function
# def onVoltageRatioChange(self, voltageRatio):
#     global calibrated, offset

#     if calibrated:
#         # Apply calibration
#         weight_newtons = (voltageRatio - offset) * gain
#         weight_grams = weight_newtons * newton_to_grams
#         timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

#         # Log weight data
#         with open(csv_filename, mode="a", newline="") as file:
#             writer = csv.writer(file)
#             writer.writerow([timestamp, weight_grams])

#         # Print weight for real-time monitoring
#         print(f"{timestamp} - Weight (grams): {weight_grams}")

# # Tare function
# def tareScale(ch):
#     global offset, calibrated
#     num_samples = 16

#     for _ in range(num_samples):
#         offset += ch.getVoltageRatio()
#         time.sleep(ch.getDataInterval() / 1000.0)

#     offset /= num_samples
#     print(f"Tare offset: {offset}")
#     calibrated = True

# # Function to control and log ODrive motor
# def motor_control_and_log(num_cycles, frequency):
#     try:
#         # Find ODrive
#         odrive_device = odrive.find_any(serial_number=odrive_serial_number)
#         odrive_device.clear_errors()
#         print(f"Connected to ODrive with serial {odrive_serial_number}")

#         # Configure ODrive
#         odrive_device.axis0.controller.config.control_mode = CONTROL_MODE_POSITION_CONTROL
#         odrive_device.axis0.controller.config.input_mode = INPUT_MODE_TRAP_TRAJ
#         odrive_device.axis0.trap_traj.config.vel_limit = 100
#         odrive_device.axis0.trap_traj.config.accel_limit = 100
#         odrive_device.axis0.trap_traj.config.decel_limit = 100

#         # Activate closed-loop control
#         odrive_device.axis0.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
#         time.sleep(0.1)

#         angle_limits = [-4, 4]
#         for deg_sec in frequency:
#             print(f"Starting cyclic test at {deg_sec} Hz")
#             odrive_device.axis0.controller.config.vel_limit = deg_sec

#             for cycle in range(1, num_cycles + 1):
#                 print(f"Cycle {cycle} of {num_cycles}")

#                 # Move to minimum angle limit
#                 odrive_device.axis0.controller.input_pos = angle_limits[0] / 17.3
#                 while abs(odrive_device.odrive_device.pos_vel_mapper.pos_rel - (angle_limits[0] / 17.3)) > 0.01:
#                     timestamp = time.time()
#                     position = odrive_device.odrive_device.pos_vel_mapper.pos_rel
#                     velocity = odrive_device.axis0.pos_vel_mapper.vel
#                     worksheet.append([timestamp, cycle, position, velocity])
#                     time.sleep(1 / 60)  # Log at 60 Hz

#                 # Move to maximum angle limit
#                 odrive_device.axis0.controller.input_pos = angle_limits[1] / 17.3
#                 while abs(odrive_device.odrive_device.pos_vel_mapper.pos_rel - (angle_limits[1] / 17.3)) > 0.01:
#                     timestamp = time.time()
#                     position = odrive_device.odrive_device.pos_vel_mapper.pos_rel
#                     velocity = odrive_device.axis0.pos_vel_mapper.vel
#                     worksheet.append([timestamp, cycle, position, velocity])
#                     time.sleep(1 / 60)

#         # Move back to zero position
#         odrive_device.axis0.controller.input_pos = 0
#         while abs(odrive_device.odrive_device.pos_vel_mapper.pos_rel - 0) > 0.01:
#             time.sleep(0.01)

#         odrive_device.axis0.requested_state = AXIS_STATE_IDLE
#         print("Motor test completed.")
#         workbook.save(excel_filename)
#         print(f"Motor data saved to {excel_filename}")

#     except Exception as e:
#         print(f"Motor control error: {e}")

# # Main function
# def main():

#     # Get user input
#     cycles_input = input("How many cycles do you want to perform? ")
#     if cycles_input.isdigit():
#         num_cycles = int(cycles_input)
#     else:
#         print("Invalid number of cycles.")
#         return
    
#     # Frequency in Hz
#     frequency = [0.8]

#     # Start motor control in a separate thread
#     motor_thread = threading.Thread(target=motor_control_and_log, args=(num_cycles, frequency))
#     motor_thread.start()
    
#     voltageRatioInput1 = VoltageRatioInput()
#     voltageRatioInput1.setChannel(1)
#     voltageRatioInput1.setOnVoltageRatioChangeHandler(onVoltageRatioChange)
#     voltageRatioInput1.openWaitForAttachment(5000)
#     voltageRatioInput1.setDataInterval(50)

#     print("Taring scale...")
#     tareScale(voltageRatioInput1)
#     print("Scale tared.")


#     try:
#         input("Press Enter to stop logging...\n")
#     except (Exception, KeyboardInterrupt):
#         pass

#     voltageRatioInput1.close()
#     motor_thread.join()
#     print("Program terminated.")

# if __name__ == "__main__":
#     main()









































































































































































# import csv
# import time
# import matplotlib.pyplot as plt
# from matplotlib.animation import FuncAnimation
# from Phidget22.Phidget import *
# from Phidget22.Devices.VoltageRatioInput import *
# from odrive.enums import *
# import odrive

# # Initialize the ODrive
# odrive_serial_number = "3943355F3231"
# odrive = odrive.find_any(serial_number=odrive_serial_number)

# # Clear ODrive errors
# odrive.clear_errors()

# # Check ODrive connection
# if odrive is not None:
#     print(f"Connected to ODrive S1 with serial number {odrive_serial_number}")

# # Set control mode and input mode
# odrive.axis0.controller.config.control_mode = CONTROL_MODE_POSITION_CONTROL
# odrive.axis0.controller.config.input_mode = INPUT_MODE_TRAP_TRAJ

# # Set trajectory control parameters
# odrive.axis0.trap_traj.config.vel_limit = 1000  # Velocity limit in turns/s
# odrive.axis0.trap_traj.config.accel_limit = 100  # Acceleration limit in turns/s^2
# odrive.axis0.trap_traj.config.decel_limit = 100  # Deceleration limit in turns/s^2

# # Activate closed-loop control
# odrive.axis0.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
# time.sleep(0.1)  # Give some time for the state transition

# # CSV file setup
# csv_file = "odrive_force_readings.csv"

# with open(csv_file, mode='w', newline='') as file:
#     writer = csv.writer(file)
#     writer.writerow(["Timestamp", "ODrive Position (turns)", "Force (grams)"])

# # Phidget setup
# gain = -8133.8  # Example gain value
# offset = 0
# calibrated = False

# # Real-time data lists
# positions = []
# forces = []

# def tare_scale(ch):
#     global offset, calibrated
#     num_samples = 16
#     offset = sum(ch.getVoltageRatio() for _ in range(num_samples)) / num_samples
#     time.sleep(3)
#     calibrated = True

# def log_to_csv(timestamp, position, force_grams):
#     with open(csv_file, mode='a', newline='') as file:
#         writer = csv.writer(file)
#         writer.writerow([timestamp, position, force_grams])
#     print(f"Logged: {timestamp}, Position: {position}, Force: {force_grams} grams")

# # Plotting setup
# plt.ion()
# fig, ax = plt.subplots()
# line, = ax.plot([], [], '-o', label='Force vs Position')
# ax.set_xlabel('Position (turns)')
# ax.set_ylabel('Force (grams)')
# ax.set_title('Real-Time Force vs Position')
# ax.legend()

# def update_plot():
#     """Update the plot in real-time."""
#     line.set_data(positions, forces)
#     ax.relim()
#     ax.autoscale_view()
#     plt.pause(0.01)

# # Main control loop
# voltageRatioInput1 = VoltageRatioInput()
# voltageRatioInput1.setChannel(1)  # Set to the correct channel
# voltageRatioInput1.openWaitForAttachment(5000)
# tare_scale(voltageRatioInput1)

# angle_limits = [-5, 5]  # Limits in turns
# frequency = [0.8]  # Frequency in Hz

# readings_per_second = 60  # 20 Hz
# interval = 1 / readings_per_second  # Interval between readings in seconds

# while True:
#     readings = input("How many total readings do you want to take? ")

#     if readings.isdigit():
#         readings = int(readings)
#         print(f"You want to take {readings} readings.")
#     else:
#         print("Please enter a valid integer.")
#         continue

#     response = input("Are you ready to start Y/n? ")
#     if response.lower() == "y":
#         for deg_sec in frequency:
#             print(f"Starting cyclic test at {deg_sec} Hz")
#             odrive.axis0.controller.config.vel_limit = deg_sec

#             for _ in range(readings // len(angle_limits)):
#                 for target in angle_limits:
#                     # Move to target position
#                     odrive.axis0.controller.input_pos = target / 17.3
#                     while abs(odrive.odrive_device.pos_vel_mapper.pos_rel - (target / 17.3)) > 0.01:
#                         current_position = odrive.odrive_device.pos_vel_mapper.pos_rel * 17.3
#                         voltage_ratio = voltageRatioInput1.getVoltageRatio()
#                         force_grams = (voltage_ratio - offset) * gain * 1000  # Convert to grams
#                         timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
#                         log_to_csv(timestamp, current_position, force_grams)
                        
#                         # Append to real-time data lists
#                         positions.append(current_position)
#                         forces.append(force_grams)
#                         update_plot()

#                         time.sleep(interval)

#         # Move to zero position
#         odrive.axis0.controller.input_pos = 0
#         while abs(odrive.odrive_device.pos_vel_mapper.pos_rel) > 0.01:
#             current_position = odrive.odrive_device.pos_vel_mapper.pos_rel * 17.3
#             voltage_ratio = voltageRatioInput1.getVoltageRatio()
#             force_grams = (voltage_ratio - offset) * gain * 1000
#             timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
#             log_to_csv(timestamp, current_position, force_grams)
            
#             # Append to real-time data lists
#             positions.append(current_position)
#             forces.append(force_grams)
#             update_plot()

#             time.sleep(interval)

#         # Set ODrive to idle state
#         odrive.axis0.requested_state = AXIS_STATE_IDLE
#         print("Test completed.")
#         break

#     elif response.lower() == "n":
#         print("Aborting...")
#         odrive.axis0.requested_state = AXIS_STATE_IDLE
#         break

#     else:
#         print("Invalid input. Please enter Y or n.")













# import csv
# import time
# from Phidget22.Phidget import *
# from Phidget22.Devices.VoltageRatioInput import *
# from odrive.enums import *
# import odrive

# # Initialize the ODrive
# odrive_serial_number = "3943355F3231"
# odrive = odrive.find_any(serial_number=odrive_serial_number)

# # Clear ODrive errors
# odrive.clear_errors()

# # Check ODrive connection
# if odrive is not None:
#     print(f"Connected to ODrive S1 with serial number {odrive_serial_number}")

# # Set control mode and input mode
# odrive.axis0.controller.config.control_mode = CONTROL_MODE_POSITION_CONTROL
# odrive.axis0.controller.config.input_mode = INPUT_MODE_TRAP_TRAJ

# # Set trajectory control parameters
# odrive.axis0.trap_traj.config.vel_limit = 1000  # Velocity limit in turns/s
# odrive.axis0.trap_traj.config.accel_limit = 1000  # Acceleration limit in turns/s^2
# odrive.axis0.trap_traj.config.decel_limit = 1000  # Deceleration limit in turns/s^2

# # Activate closed-loop control
# odrive.axis0.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
# time.sleep(0.1)  # Give some time for the state transition

# # CSV file setup
# csv_file = "odrive_force_readings.csv"

# with open(csv_file, mode='w', newline='') as file:
#     writer = csv.writer(file)
#     writer.writerow(["Timestamp", "ODrive Position (turns)", "Force (grams)"])

# # Phidget setup
# gain = -8133.8  # Example gain value
# offset = 0
# calibrated = False

# def tare_scale(ch):
#     global offset, calibrated
#     num_samples = 16
#     offset = sum(ch.getVoltageRatio() for _ in range(num_samples)) / num_samples
#     calibrated = True

# def log_to_csv(timestamp, position, force_grams):
#     with open(csv_file, mode='a', newline='') as file:
#         writer = csv.writer(file)
#         writer.writerow([timestamp, position, force_grams])
#     print(f"Logged: {timestamp}, Position: {position}, Force: {force_grams} grams")

# # Main control loop
# voltageRatioInput1 = VoltageRatioInput()
# voltageRatioInput1.setChannel(1)  # Set to the correct channel
# voltageRatioInput1.openWaitForAttachment(5000)
# tare_scale(voltageRatioInput1)

# angle_limits = [-5, 5]  # Limits in turns
# frequency = [1.2]  # Frequency in Hz

# while True:
#     readings = input("How many readings 1 second apart do you want to take? ")

#     if readings.isdigit():
#         readings = int(readings)
#         print(f"You want to take {readings} readings.")
#     else:
#         print("Please enter a valid integer.")
#         continue

#     response = input("Are you ready to start Y/n? ")
#     if response.lower() == "y":
#         for deg_sec in frequency:
#             print(f"Starting cyclic test at {deg_sec} Hz")
#             odrive.axis0.controller.config.vel_limit = deg_sec

#             for _ in range(readings):
#                 for target in angle_limits:
#                     # Move to target position
#                     odrive.axis0.controller.input_pos = target / 17.3
#                     while abs(odrive.odrive_device.pos_vel_mapper.pos_rel - (target / 17.3)) > 0.01:
#                         current_position = odrive.odrive_device.pos_vel_mapper.pos_rel*17.3
#                         voltage_ratio = voltageRatioInput1.getVoltageRatio()
#                         force_grams = (voltage_ratio - offset) * gain * 1000  # Convert to grams
#                         timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
#                         log_to_csv(timestamp, current_position, force_grams)
#                         time.sleep(0.01)

#         # Move to zero position
#         odrive.axis0.controller.input_pos = 0
#         while abs(odrive.odrive_device.pos_vel_mapper.pos_rel) > 0.01:
#             current_position = odrive.odrive_device.pos_vel_mapper.pos_rel*17.3
#             voltage_ratio = voltageRatioInput1.getVoltageRatio()
#             force_grams = (voltage_ratio - offset) * gain * 1000
#             timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
#             log_to_csv(timestamp, current_position, force_grams)
#             time.sleep(0.01)

#         # Set ODrive to idle state
#         odrive.axis0.requested_state = AXIS_STATE_IDLE
#         print("Test completed.")
#         break

#     elif response.lower() == "n":
#         print("Aborting...")
#         odrive.axis0.requested_state = AXIS_STATE_IDLE
#         break

#     else:
#         print("Invalid input. Please enter Y or n")





















































































# import csv
# import time
# from Phidget22.Phidget import *
# from Phidget22.Devices.VoltageRatioInput import *
# from odrive.enums import *
# import odrive

# # Initialize the ODrive
# odrive_serial_number = "3943355F3231"
# odrive = odrive.find_any(serial_number=odrive_serial_number)

# # Clear ODrive errors
# odrive.clear_errors()

# # Check ODrive connection
# if odrive is not None:
#     print(f"Connected to ODrive S1 with serial number {odrive_serial_number}")

# # Set control mode and input mode
# odrive.axis0.controller.config.control_mode = CONTROL_MODE_POSITION_CONTROL
# odrive.axis0.controller.config.input_mode = INPUT_MODE_TRAP_TRAJ

# # Set trajectory control parameters
# odrive.axis0.trap_traj.config.vel_limit = 1000  # Velocity limit in turns/s
# odrive.axis0.trap_traj.config.accel_limit = 1000  # Acceleration limit in turns/s^2
# odrive.axis0.trap_traj.config.decel_limit = 1000  # Deceleration limit in turns/s^2

# # Activate closed-loop control
# odrive.axis0.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
# time.sleep(0.1)  # Give some time for the state transition

# # CSV file setup
# csv_file = "odrive_force_readings.csv"

# with open(csv_file, mode='w', newline='') as file:
#     writer = csv.writer(file)
#     writer.writerow(["Timestamp", "ODrive Position (turns)", "Force (grams)"])

# # Phidget setup
# gain = -8133.8  # Example gain value
# offset = 0
# calibrated = False

# def tare_scale(ch):
#     global offset, calibrated
#     num_samples = 16
#     offset = sum(ch.getVoltageRatio() for _ in range(num_samples)) / num_samples
#     calibrated = True

# def log_to_csv(timestamp, position, force_grams):
#     with open(csv_file, mode='a', newline='') as file:
#         writer = csv.writer(file)
#         writer.writerow([timestamp, position, force_grams])
#     print(f"Logged: {timestamp}, Position: {position}, Force: {force_grams} grams")

# # Main control loop
# voltageRatioInput1 = VoltageRatioInput()
# voltageRatioInput1.setChannel(1)  # Set to the correct channel
# voltageRatioInput1.openWaitForAttachment(5000)
# tare_scale(voltageRatioInput1)

# angle_limits = [-5, 5]  # Limits in turns
# frequency = [0.8]  # Frequency in Hz

# while True:
#     readings = input("How many readings 1 second apart do you want to take? ")

#     if readings.isdigit():
#         readings = int(readings)
#         print(f"You want to take {readings} readings.")
#     else:
#         print("Please enter a valid integer.")
#         continue

#     response = input("Are you ready to start Y/n? ")
#     if response.lower() == "y":
#         for deg_sec in frequency:
#             print(f"Starting cyclic test at {deg_sec} Hz")
#             odrive.axis0.controller.config.vel_limit = deg_sec

#             for _ in range(readings):
#                 for target in angle_limits:
#                     # Move to target position
#                     odrive.axis0.controller.input_pos = target / 17.3
#                     while abs(odrive.odrive_device.pos_vel_mapper.pos_rel - (target / 17.3)) > 0.01:
#                         current_position = odrive.odrive_device.pos_vel_mapper.pos_rel
#                         voltage_ratio = voltageRatioInput1.getVoltageRatio()
#                         force_grams = (voltage_ratio - offset) * gain * 1000  # Convert to grams
#                         timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
#                         log_to_csv(timestamp, current_position, force_grams)
#                         time.sleep(0.01)

#         # Move to zero position
#         odrive.axis0.controller.input_pos = 0
#         while abs(odrive.odrive_device.pos_vel_mapper.pos_rel) > 0.01:
#             current_position = odrive.odrive_device.pos_vel_mapper.pos_rel
#             voltage_ratio = voltageRatioInput1.getVoltageRatio()
#             force_grams = (voltage_ratio - offset) * gain * 1000
#             timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
#             log_to_csv(timestamp, current_position, force_grams)
#             time.sleep(0.01)

#         # Set ODrive to idle state
#         odrive.axis0.requested_state = AXIS_STATE_IDLE
#         print("Test completed.")
#         break

#     elif response.lower() == "n":
#         print("Aborting...")
#         odrive.axis0.requested_state = AXIS_STATE_IDLE
#         break

#     else:
#         print("Invalid input. Please enter Y or n")





















# import odrive
# from odrive.enums import *
# import time
# import openpyxl
# import subprocess

# # Find a connected ODrive (this will block until you connect one)
# odrive_serial_number = "3943355F3231"
# odrive = odrive.find_any(serial_number=odrive_serial_number)

# # Clear ODrive S1 Errors if any
# odrive.clear_errors()

# ## Odrivetool command to backup and restore configuration
# # odrivetool backup-config my_config.json
# # odrivetool restore-config my_config.json

# # Check if the connection is successful
# if odrive is not None:
#     print(f"Connected to ODrive S1 with serial number {odrive_serial_number}")

# # Set control mode to position control and input mode to trajectory control
# odrive.axis0.controller.config.control_mode = CONTROL_MODE_POSITION_CONTROL
# odrive.axis0.controller.config.input_mode = INPUT_MODE_TRAP_TRAJ


# # Set trajectory control parameters
# odrive.axis0.trap_traj.config.vel_limit = 100  # Velocity limit in turns/s
# odrive.axis0.trap_traj.config.accel_limit = 50 # Acceleration limit in turns/s^2
# odrive.axis0.trap_traj.config.decel_limit = 50  # Deceleration limit in turns/s^2
# # odrive.axis0.trap_traj.config.A_per_css = 0.0  # Acceleration smoothing, set to 0 to disable

# # Activate closed-loop control
# odrive.axis0.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
# time.sleep(0.1)  # Give some time for the state transition

# # Excel File Name
# file_name = "Motor_Angle_Cyclic_Test.xlsx"


# # Angle Limits (in turns)
# angle_limits = [-3, 3]  # Arm will oscillate between these angles
# frequency = [0.5] # Frequency in Hz

# start_offset = odrive.odrive_device.pos_vel_mapper.pos_rel
# print(f"start offset is {start_offset}")


# while True:
#     readings = input("How many readings 1 second apart do you want to take? ")

#     if readings.isdigit():
#         readings = int(readings)
#         print(f"You want to take {readings} readings.")
#     else:
#         print("Please enter a valid integer.")
#         continue

#     response = input("Are you ready to start Y/n? ")
#     if response in ["Y", "y"]:
#         for deg_sec in frequency:
#             print(f"Starting cyclic test at {deg_sec} deg/sec")

#             # Calculate velocity limit
#             print(deg_sec)
#             # velocity = (deg_sec*60/6)/60/6 # Set calculated velocity limit
#             velocity = deg_sec
#             odrive.axis0.controller.config.vel_limit = velocity
#             print(f"velocity: {velocity}")

#             for i in range(readings):
#                 # Move to minimum angle limit
#                 odrive.axis0.controller.input_pos = angle_limits[0]/17.3
#                 print("cycle 1")
#                 while abs(odrive.odrive_device.pos_vel_mapper.pos_rel - (angle_limits[0]/17.3)) > 0.01:
#                     time.sleep(0.01)

#                 # time.sleep(5)

#                 # Move to maximum angle limit
#                 odrive.axis0.controller.input_pos = angle_limits[1]/17.3
#                 print("cycle 2")
#                 while abs(odrive.odrive_device.pos_vel_mapper.pos_rel - (angle_limits[1]/17.3))> 0.01:
#                     time.sleep(0.01)

#                 # time.sleep(5)
                
#             print(f"Completed {readings} cycles at {deg_sec} Hz")

#         # Move to maximum angle limit
#         odrive.axis0.controller.input_pos = 0
#         while abs(odrive.odrive_device.pos_vel_mapper.pos_rel - 0) > 0.01:
#             print(abs(odrive.odrive_device.pos_vel_mapper.pos_rel))
#             time.sleep(0.01)
#         # Set ODrive State to Idle
#         odrive.axis0.requested_state = AXIS_STATE_IDLE
#         print(f"Completed {readings} cycles at {deg_sec} Hz")
#         break

#     elif response in ["n", "N"]:
#         print("Aborting...")
#         # Set ODrive State to Idle
#         odrive.axis0.requested_state = AXIS_STATE_IDLE
#         break

#     else:
#         print("Invalid input. Please enter Y or n")

