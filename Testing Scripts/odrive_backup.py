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
# odrive.axis0.trap_traj.config.accel_limit = 100 # Acceleration limit in turns/s^2
# odrive.axis0.trap_traj.config.decel_limit = 100  # Deceleration limit in turns/s^2
# # odrive.axis0.trap_traj.config.A_per_css = 0.0  # Acceleration smoothing, set to 0 to disable

# # Activate closed-loop control
# odrive.axis0.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
# time.sleep(0.1)  # Give some time for the state transition

# # Excel File Name
# file_name = "Motor_Angle_Cyclic_Test.xlsx"

# # period = 1 / frequency_set_points[0]
# # odrive.axis0.controller.input_pos = angle_limits[0]/17.3

# # #Raw Gearbox Position to ODrive Position and deg/sec
# # deg_sec = 360
# # pos_angle = 360
# # odrive.axis0.trap_traj.config.vel_limit = (deg_sec*60/6)/60/6 # Set calculated velocity limit
# # odrive.axis0.controller.input_pos = pos_angle/360*10

# # Angle Limits (in turns)
# angle_limits = [-4, 4]  # Arm will oscillate between these angles
# frequency = [0.8] # Frequency in Hz

# start_offset = odrive.axis0.pos_vel_mapper.pos_rel
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
#                 while abs(odrive.axis0.pos_vel_mapper.pos_rel - (angle_limits[0]/17.3)) > 0.01:
#                     time.sleep(0.01)

#                 # time.sleep(5)

#                 # Move to maximum angle limit
#                 odrive.axis0.controller.input_pos = angle_limits[1]/17.3
#                 print("cycle 2")
#                 while abs(odrive.axis0.pos_vel_mapper.pos_rel - (angle_limits[1]/17.3))> 0.01:
#                     time.sleep(0.01)

#                 # time.sleep(5)
                
#             print(f"Completed {readings} cycles at {deg_sec} Hz")

#         # Move to maximum angle limit
#         odrive.axis0.controller.input_pos = 0
#         while abs(odrive.axis0.pos_vel_mapper.pos_rel - 0) > 0.01:
#             print(abs(odrive.axis0.pos_vel_mapper.pos_rel))
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


#         # odrv0.axis0.motor.effective_current_lim=45.333335876464844
















import odrive
from odrive.enums import *
import time
import openpyxl

# Find a connected ODrive (this will block until you connect one)
odrive_serial_number = "3943355F3231"
odrive = odrive.find_any(serial_number=odrive_serial_number)

# Clear ODrive S1 Errors if any
odrive.clear_errors()

# Check if the connection is successful
if odrive is not None:
    print(f"Connected to ODrive S1 with serial number {odrive_serial_number}")

# Set control mode to position control and input mode to trajectory control
odrive.axis0.controller.config.control_mode = CONTROL_MODE_POSITION_CONTROL
odrive.axis0.controller.config.input_mode = INPUT_MODE_TRAP_TRAJ

# Set trajectory control parameters
odrive.axis0.trap_traj.config.vel_limit = 100  # Velocity limit in turns/s
odrive.axis0.trap_traj.config.accel_limit = 100  # Acceleration limit in turns/s^2
odrive.axis0.trap_traj.config.decel_limit = 100  # Deceleration limit in turns/s^2

# Activate closed-loop control
odrive.axis0.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
time.sleep(0.1)  # Give some time for the state transition

# Excel File Name
file_name = "Motor_Angle_Cyclic_Test.xlsx"

# Initialize Excel workbook and worksheet
workbook = openpyxl.Workbook()
worksheet = workbook.active
worksheet.title = "Test Data"
worksheet.append(["Timestamp (s)", "Cycle", "Position (turns)", "Velocity (turns/s)"])

# Angle Limits (in turns)
angle_limits = [-4, 4]  # Arm will oscillate between these angles
frequency = [0.8]  # Frequency in Hz

start_offset = odrive.axis0.pos_vel_mapper.pos_rel
print(f"Start offset is {start_offset}")

while True:
    cycles_input = input("How many cycles do you want to perform? ")

    if cycles_input.isdigit():
        num_cycles = int(cycles_input)
        print(f"You want to perform {num_cycles} cycles.")
    else:
        print("Please enter a valid integer.")
        continue

    response = input("Are you ready to start Y/n? ")
    if response in ["Y", "y"]:
        for deg_sec in frequency:
            print(f"Starting cyclic test at {deg_sec} deg/sec")

            # Calculate velocity limit
            velocity = deg_sec
            odrive.axis0.controller.config.vel_limit = velocity
            print(f"Velocity: {velocity}")

            for cycle in range(1, num_cycles + 1):
                print(f"Cycle {cycle} of {num_cycles}")

                # Move to minimum angle limit
                odrive.axis0.controller.input_pos = angle_limits[0] / 17.3
                while abs(odrive.axis0.pos_vel_mapper.pos_rel - (angle_limits[0] / 17.3)) > 0.01:
                    # Record data at 60 Hz
                    timestamp = time.time()
                    position = odrive.axis0.pos_vel_mapper.pos_rel
                    velocity = odrive.axis0.pos_vel_mapper.vel
                    worksheet.append([timestamp, cycle, position, velocity])
                    time.sleep(1 / 60)  # 60 Hz refresh rate

                # Move to maximum angle limit
                odrive.axis0.controller.input_pos = angle_limits[1] / 17.3
                while abs(odrive.axis0.pos_vel_mapper.pos_rel - (angle_limits[1] / 17.3)) > 0.01:
                    # Record data at 60 Hz
                    timestamp = time.time()
                    position = odrive.axis0.pos_vel_mapper.pos_rel
                    velocity = odrive.axis0.pos_vel_mapper.vel
                    worksheet.append([timestamp, cycle, position, velocity])
                    time.sleep(1 / 60)  # 60 Hz refresh rate

            print(f"Completed {num_cycles} cycles at {deg_sec} Hz")

        # Move back to the zero position
        odrive.axis0.controller.input_pos = 0
        while abs(odrive.axis0.pos_vel_mapper.pos_rel - 0) > 0.01:
            time.sleep(0.01)

        # Set ODrive State to Idle
        odrive.axis0.requested_state = AXIS_STATE_IDLE
        print("Test completed.")

        # Save the Excel file
        workbook.save(file_name)
        print(f"Data saved to {file_name}.")
        break

    elif response in ["n", "N"]:
        print("Aborting...")
        # Set ODrive State to Idle
        odrive.axis0.requested_state = AXIS_STATE_IDLE
        break

    else:
        print("Invalid input. Please enter Y or n.")
