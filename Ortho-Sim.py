import os
import sys  # Add sys import for PyQt compatibility
import math  # Add math import for torque calculations

# Import the Timer from the threading module
from threading import Timer
import concurrent.futures

import pywinstyles

import tkinter as tk
import customtkinter as ctk
from CTkMessagebox import CTkMessagebox

from customtkinter import set_default_color_theme

import serial
import csv
import threading
import time
from serial.tools.list_ports import comports
import ctypes
import webbrowser

import PIL
from PIL import Image

# Import Phidget
from Phidget22.Phidget import *
from Phidget22.Devices.VoltageRatioInput import *
import time

# Import Odrive
import odrive
from odrive.enums import *

# Import PyQtGraph for plotting
import pyqtgraph as pg
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont

# Phidget calibration parameters
# gain = -8133.8  # Example value
gain = 25014.7939492599
offset = 0
newton_to_grams = 1000
calibrated = False

# Variable to track if plot window is open
plot_window_open = False
# Global variables for plot data
angle_data = []
torque_data = []  # Changed from weight_data to torque_data
plot_window = None
plot_curve = None
plot_timer = None

class MovingAverageFilter:
    def __init__(self, window_size):
        self.window_size = window_size
        self.values = []

    def add_value(self, value):
        self.values.append(value)
        if len(self.values) > self.window_size:
            self.values.pop(0)

    def get_smoothed_value(self):
        if not self.values:
            return None
        return sum(self.values) / len(self.values)

class MyInterface:
    def __init__(self, master):
        self.master = master
        self.master.title("OrthoSim")

        # Threadding flags
        self.odrive_ctrl = False
        self.monitor_odrive_conn = False
        self.strain_test_active = False
        self.strain_data_buffer = []
        self.starting_position = 0  # Initialize starting position
        self.current_cycle = 0  # Add cycle counter
        
        # Add continuous movement flags
        self.continuous_movement_active = False
        self.movement_direction = None
        self.movement_timer = None
        
        # Add manual mode flag
        self.manual_mode = ctk.BooleanVar(value=False)
        
        # Frequency tracking variables
        self.last_sample_time = 0
        self.sample_count = 0
        self.frequency_buffer = []
        self.frequency_update_interval = 1.0  # Update frequency display every 1 second
        self.last_logged_time = 0  # Track the last logged timestamp
        self.min_time_between_samples = 0.008  # Minimum 8ms between samples (125Hz)
        
        # Deduplication variables
        self.last_voltage_ratio = None
        self.last_angle = None
        self.last_weight = None
        
        # Moving average filters for both plot and data logging
        self.angle_filter = MovingAverageFilter(window_size=30)  # Increased window size for smoother data
        self.weight_filter = MovingAverageFilter(window_size=30)  # Increased window size for smoother data
        self.torque_filter = MovingAverageFilter(window_size=30)  # Increased window size for smoother data

        set_default_color_theme("dark-blue")
        ctk.set_appearance_mode("dark")

        self.setup_ui()

        # Your existing initialization code here
        self.moving_avg_filter = MovingAverageFilter(window_size=8)  # Create an instance of MovingAverageFilter

        # Old Threading flags
        self.logging_active = False  # Flag to indicate whether logging is active
        self.live_update_flag = True  # Flag to control live update thread

        # Bind window events
        self.master.bind('<Configure>', self.on_window_move)
        self.master.bind('<Unmap>', self.on_window_minimize)
        self.master.bind('<Map>', self.on_window_restore)
        self.master.bind('<FocusIn>', self.on_window_restore)  # Add binding for focus events

    def on_window_move(self, event):
        """Update plot window position when main window moves"""
        # Only respond to window movement events
        if event.widget == self.master and hasattr(self, 'plot_container'):
            # Update plot window position relative to main window
            self.plot_container.move(self.master.winfo_x() + 450, self.master.winfo_y() + 190)

    def on_window_minimize(self, event):
        """Hide plot window when main window is minimized"""
        if hasattr(self, 'plot_container'):
            self.plot_container.hide()

    def on_window_restore(self, event):
        """Show plot window when main window is restored"""
        if hasattr(self, 'plot_container'):
            self.plot_container.show()
            self.plot_container.raise_()
        elif plot_window_open:
            # If plot window was open but container was lost, recreate it
            self.create_plot_window()

    def setup_ui(self):
        
        image = PIL.Image.open("images/background_image.png")
        background_image = ctk.CTkImage(image, size=(1242, 786))

        # Create a bg label
        bg_lbl = ctk.CTkLabel(self.master, text="", image=background_image)
        bg_lbl.place(x=0, y=0)

        # Header Frame
        header_frame = ctk.CTkFrame(master=self.master, bg_color="#000001", fg_color="#000001")  # Use CTkFrame
        pywinstyles.set_opacity(header_frame, color="#000001") # just add this line
        header_frame.pack(pady=10, padx=10)

        IMAGE_WIDTH = 255*1.5
        IMAGE_HEIGHT = 68.2*1.5

        image = ctk.CTkImage(light_image=Image.open("images/SpinSync_logo.png"), dark_image=Image.open("images/SpinSync_logo.png"), size=(IMAGE_WIDTH , IMAGE_HEIGHT))
        

        # Create a label to display the image
        image_label = ctk.CTkLabel(header_frame, image=image, text='', corner_radius=60)
        image_label.grid(row=0, column=0, columnspan=3, pady=10, padx=10)  # Span across all columns


        # Create frame for input ranges
        inputs_frame = ctk.CTkFrame(self.master, bg_color="#000001", fg_color="#000001")  # Use CTkFrame
        pywinstyles.set_opacity(inputs_frame, color="#000001") # just add this line
        inputs_frame.place(x=45, y=150+20-70)  # Moved up by adjusting y position

        # Create input fields in a grid form for input values 

        self.file_name_input = ctk.CTkEntry(inputs_frame, width=345/2-5, placeholder_text="File Name (Prefix)")
        self.file_name_input.grid(row=1, column=0, padx=5, pady=5)

        self.cycles_input = ctk.CTkEntry(inputs_frame, width=345/2-5, placeholder_text="Cycles")
        self.cycles_input.grid(row=1, column=1, padx=5, pady=5)

        self.speed_input = ctk.CTkEntry(inputs_frame, width=345/2-5, placeholder_text="Speed (Degrees/Second)")
        self.speed_input.grid(row=2, column=0, padx=5, pady=5)

        self.acceleration_input = ctk.CTkEntry(inputs_frame, width=345/2-5, placeholder_text="Acceleration (Degrees/s^2)")
        self.acceleration_input.grid(row=2, column=1, padx=5, pady=5)

        self.min_angle_input = ctk.CTkEntry(inputs_frame, width=345/2-5, placeholder_text="Min Angle (Degrees)")
        self.min_angle_input.grid(row=3, column=0, padx=5, pady=5)
        self.min_angle_input.bind('<KeyRelease>', self.validate_angle_input)

        self.max_angle_input = ctk.CTkEntry(inputs_frame, width=345/2-5, placeholder_text="Max Angle (Degrees)")
        self.max_angle_input.grid(row=3, column=1, padx=5, pady=5)
        self.max_angle_input.bind('<KeyRelease>', self.validate_angle_input)

        # Create four buttons stacked vertically
        button_names = ["Connect", "Start", "Stop", "Reset"]
        commands = [self.connect_system, self.start_strain_test, self.stop_logging, self.reset_display]
        button_colour = ["#28a745", "#007bff", "#dc3545", "#cc8400"]
        start_button_position_x = 50
        start_button_position_y = 310+20-100  # Moved up by adjusting y position

        button_positions_y = [start_button_position_y+0, start_button_position_y+37, start_button_position_y+74, start_button_position_y+111]
        self.buttons = []
        for name, command, colour, position_y in zip(button_names, commands, button_colour, button_positions_y):
            button = ctk.CTkButton(self.master, text=name, command=command, hover_color="grey", width=340, fg_color=colour, corner_radius=20, bg_color="#000001")
            button.pack(pady=5, padx = 20)  # Use pack with pady for vertical spacing
            self.buttons.append(button)
            self.buttons[-1].place(x=start_button_position_x, y= position_y)
            pywinstyles.set_opacity(button, color="#000001") # just add this line

        # Add manual control frame below the buttons
        manual_control_frame = ctk.CTkFrame(self.master, fg_color="#000001", bg_color="#000001")
        manual_control_frame.place(x=45, y=start_button_position_y+160)  # Position below the buttons
        pywinstyles.set_opacity(manual_control_frame, color="#000001") # just add this line

        # Add step angle input with validation
        self.step_angle_input = ctk.CTkEntry(manual_control_frame, width=150, placeholder_text="Step Angle (0-10 deg)")
        self.step_angle_input.grid(row=0, column=0, padx=5, pady=5)
        self.step_angle_input.bind('<KeyRelease>', self.validate_step_angle)

        # Add manual mode toggle
        self.manual_mode_toggle = ctk.CTkSwitch(manual_control_frame, text="Manual Mode", 
                                              variable=self.manual_mode,
                                              onvalue=True, offvalue=False,
                                              command=self.toggle_manual_mode)
        self.manual_mode_toggle.grid(row=0, column=1, padx=5, pady=5)

        # Add arrow buttons frame
        arrow_frame = ctk.CTkFrame(manual_control_frame, fg_color="#000001", bg_color="#000001")
        arrow_frame.grid(row=1, column=0, columnspan=2, padx=5, pady=5)

        # Add left arrow button
        self.left_arrow = ctk.CTkButton(arrow_frame, text="←", width=50, height=50,
                                      command=self.move_motor_left)
        self.left_arrow.grid(row=0, column=0, padx=5, pady=5)
        # Add button release binding
        self.left_arrow.bind('<ButtonRelease-1>', lambda e: self.stop_continuous_movement())

        # Add right arrow button
        self.right_arrow = ctk.CTkButton(arrow_frame, text="→", width=50, height=50,
                                       command=self.move_motor_right)
        self.right_arrow.grid(row=0, column=1, padx=5, pady=5)
        # Add button release binding
        self.right_arrow.bind('<ButtonRelease-1>', lambda e: self.stop_continuous_movement())

        # Add continuous/step mode toggle next to arrows
        self.continuous_mode = ctk.BooleanVar(value=False)
        self.mode_toggle = ctk.CTkSwitch(arrow_frame, text="Continuous Mode", 
                                       variable=self.continuous_mode,
                                       onvalue=True, offvalue=False)
        self.mode_toggle.grid(row=0, column=2, padx=5, pady=5)

        # Disable manual control buttons initially
        self.left_arrow.configure(state="disabled")
        self.right_arrow.configure(state="disabled")
        self.step_angle_input.configure(state="disabled")
        self.mode_toggle.configure(state="disabled")
        
        # Disable Start button initially (until system is connected)
        self.buttons[1].configure(state="disabled")  # Index 1 is the "Start" button

        # Create frame for the bottom section (terminal)
        terminal_frame = ctk.CTkFrame(master=self.master, bg_color="#000001", fg_color="#000001")  # Use CTkFrame
        pywinstyles.set_opacity(terminal_frame, color="#000001") # just add this line
        terminal_frame.place(x=35, y=452+20+35)  # Moved up by adjusting y position

        # Terminal (text output)
        self.terminal = ctk.CTkTextbox(terminal_frame, height=180, width=350, corner_radius=20)
        self.terminal.pack(pady=10, padx=10)


        # Create frame for the footer section with a larger width
        footer_frame = ctk.CTkFrame(master=self.master, width=200, bg_color="#000001", corner_radius=20)  # Set a larger width
        # pywinstyles.set_opacity(footer_frame, value=0.85, color="#000001") # just add this line
        pywinstyles.set_opacity(footer_frame, value=0.85, color="#000001") # just add this line

        # footer_frame.pack(pady=10, padx=10)  # Use fill='x' to make the frame fill the entire width
        footer_frame.place(x=35, y=720)

        # Developer label
        developer_label = ctk.CTkLabel(footer_frame, text="Developed By: ", anchor="w", font=("Arial", 12, "bold"), text_color="white")
        developer_label.grid(row=0, column=0, sticky="w", padx=10, pady=5)  # Adjust padx as needed

        # Developer's name with hyperlink
        developer_name_label = ctk.CTkLabel(footer_frame, text="Brock Cooper", anchor="w", cursor="hand2", text_color="#007bff", font=("Arial", 12, "bold"))
        developer_name_label.grid(row=0, column=0, sticky="w", padx=95, pady=5)  # Adjust padx as needed
        developer_name_label.bind("<Button-1>", lambda event: self.open_website("https://brockcooper.au"))

        # space
        space_label = ctk.CTkLabel(footer_frame, text="", anchor="e")
        space_label.grid(row=0, column=2, sticky="e", padx=454, pady=5)  # Adjust padx as needed

        # Version label
        version_label = ctk.CTkLabel(footer_frame, text="Version 1.0", anchor="e", font=("Arial", 12, "bold"), text_color="white")
        version_label.grid(row=0, column=2, sticky="e", padx=10, pady=5)  # Adjust padx as needed

        # Handle window closing event
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)
 
    def open_website(self, url):
            webbrowser.open_new(url)
            
    def change_theme(self, choice):
        ctk.set_appearance_mode(choice)

    def onVoltageRatioChange(self, voltageRatio):
        # Unused function - can be removed
        self.readings = []
        self.readings.append(voltageRatio)
        print("Reading: " + str(voltageRatio))   

    def find_odrive_with_timeout(serial_number, timeout=5):
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                odrv = odrive.find_any(serial_number=serial_number, timeout=1)  # Short timeout for each attempt
                if odrv:
                    return odrv
            except Exception:
                pass
            time.sleep(0.1)  # Short delay between attempts
        return None


    def connect_system(self): 
        self.clear_terminal()
        self.live_update_flag = False  # Reset live update flag

        try:
            # Retrieve the file name as a string (no checks needed here)
            file_name = self.file_name_input.get()
            
            if not self.manual_mode.get():
                # Only validate inputs if not in manual mode
                try:
                    # Attempt to parse cycles, speed, acceleration, min_angle, and max_angle as float or int
                    self.odrive_cycles = float(self.cycles_input.get())
                    self.odrive_speed = float(self.speed_input.get())
                    odrive_accel = float(self.acceleration_input.get())
                    min_angle = float(self.min_angle_input.get())
                    max_angle = float(self.max_angle_input.get())

                    # Optional: Convert to int if they should be whole numbers
                    self.odrive_cycles = int(self.cycles_input.get())
                    
                    print("All inputs are valid.")

                except ValueError:
                    print("Invalid input detected. Please enter numeric values for cycles, speed, acceleration, min angle, and max angle.")
                    CTkMessagebox(title="Input Error", message="Please enter numeric values for cycles, speed, acceleration, min angle, and max angle.")
                    return
            else:
                # Use default values for manual mode
                self.odrive_speed = 10.0
                odrive_accel = 10.0
                # Set default angle limits for manual mode
                min_angle = 0.0
                max_angle = 0.0
                self.update_terminal("Manual mode enabled - using default speed and acceleration values\n")
            
            odrive_serial_number = "3943355F3231"
            timeout_duration = 5

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(MyInterface.find_odrive_with_timeout, odrive_serial_number, timeout_duration)
                self.odrive_controller = future.result(timeout=timeout_duration)

                if self.odrive_controller is None:
                    self.update_terminal("No serial connection established. Please connect ODrive.\n")
                    # Ensure Start button remains disabled if connection fails
                    self.buttons[1].configure(state="disabled")
                    return
                
                # Clear ODrive S1 Errors if any
                self.odrive_controller.clear_errors()
                self.update_terminal("ODrive connected successfully.\n")
                
                # Enable Start button now that system is connected (only if not in manual mode)
                if not self.manual_mode.get():
                    self.buttons[1].configure(state="normal")  # Index 1 is the "Start" button
                
                # Set control mode only if odrive_controller is connected
                if self.odrive_controller:
                    self.odrive_controller.axis0.controller.config.control_mode = CONTROL_MODE_POSITION_CONTROL
                    
                    # Enable manual control buttons if in manual mode
                    if self.manual_mode.get():
                        self.toggle_manual_mode()
                    else:
                        # Enable manual control buttons
                        self.left_arrow.configure(state="normal")
                        self.right_arrow.configure(state="normal")
                        self.step_angle_input.configure(state="normal")
                        self.mode_toggle.configure(state="normal")
                    
                    # Store initial position for reference
                    self.starting_position = self.odrive_controller.axis0.pos_vel_mapper.pos_rel
                    
                    # Set angle limits (only used in non-manual mode)
                    if not self.manual_mode.get():
                        self.angle_limits = [-min_angle, max_angle]  # Arm will oscillate between these angles

        except concurrent.futures.TimeoutError:
            self.update_terminal(f"Connection attempt timed out after {timeout_duration} seconds.\n")
            self.update_terminal(f"Unable to establish connection to Odrive.\n")
            # Ensure Start button remains disabled if connection times out
            self.buttons[1].configure(state="disabled")
            return
        except Exception as e:
            self.update_terminal(f"Error connecting to ODrive: {e}\n")
            # Ensure Start button remains disabled if connection fails
            self.buttons[1].configure(state="disabled")
            return

        # Check if the connection is successful
        if odrive is not None:
            self.update_terminal(f"Connected to ODrive S1\nSerial Number: {odrive_serial_number}\n")
            # print(f"Connected to ODrive S1 with serial number {odrive_serial_number}")

        # Set control mode to position control and input mode to trajectory control
        self.odrive_controller.axis0.controller.config.control_mode = CONTROL_MODE_POSITION_CONTROL
        self.odrive_controller.axis0.controller.config.input_mode = INPUT_MODE_TRAP_TRAJ

        # Tune motor parameters for low-speed operation with gearbox
        try:
            # # Increase current limits for smoother low-speed operation
            # self.odrive_controller.axis0.controller.config.dc_max_positive_current = 120.0  # Increase current limit (adjust based on your motor)
            # self.odrive_controller.axis0.motor.calibration_current = 5.0  # Calibration current
            
            # Adjust controller gains for better low-speed performance
            self.odrive_controller.axis0.controller.config.pos_gain = 26.600000381469727  # Position gain (default is often too high)
            self.odrive_controller.axis0.controller.config.vel_gain = 0.8105000257492065  # Velocity gain
            self.odrive_controller.axis0.controller.config.vel_integrator_gain = 2.385293960571289  # Velocity integrator gain
            
            # Set trajectory control parameters
            self.odrive_controller.axis0.trap_traj.config.vel_limit = 500  # Velocity limit in turns/s
            # Convert acceleration from degrees/second² to turns/second² using velocity factor
            accel_turns_per_sec2 = odrive_accel / 2.455  # Use velocity factor for acceleration
            self.odrive_controller.axis0.trap_traj.config.accel_limit = accel_turns_per_sec2  # Acceleration limit in turns/s^2
            self.odrive_controller.axis0.trap_traj.config.decel_limit = accel_turns_per_sec2  # Deceleration limit in turns/s^2
            
            # # Add smoothing to reduce jitter
            # self.odrive_controller.axis0.trap_traj.config.A_per_css = 0.5  # Acceleration smoothing (0.0 to 1.0)
            
            # Adjust velocity ramp rate for smoother acceleration
            self.odrive_controller.axis0.controller.config.vel_ramp_rate = 1.0  # Velocity ramp rate in turns/s^2
            
            self.update_terminal("Motor parameters tuned for low-speed operation with gearbox\n")
        except Exception as e:
            self.update_terminal(f"Error tuning motor parameters: {e}\n")
            self.update_terminal("Continuing with default parameters\n")
        
        # Activate closed-loop control
        self.odrive_controller.axis0.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
        time.sleep(0.1)  # Give some time for the state transition

        # Angle Limits (in turns)
        self.angle_limits = [-min_angle, max_angle]  # Arm will oscillate between these angles

    def disconnect_odrive(self):
        """Disconnect from ODrive safely"""
        try:
            if hasattr(self, 'odrive_controller') and self.odrive_controller:
                # Set ODrive State to Idle
                self.odrive_controller.axis0.requested_state = AXIS_STATE_IDLE
                self.update_terminal("ODrive disconnected and set to idle state\n")
        except Exception as e:
            self.update_terminal(f"Error disconnecting ODrive: {e}\n")

    def monitor_odrive_connection():
        # Unused function - can be removed
        while odrive is not None:
            time.sleep(0.5)
        else:
            print("disconnected")
            return  
                

    def odrive_control(self):
        """Control the ODrive Motor"""
        try:
            # Activate closed-loop control
            self.odrive_controller.axis0.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
            time.sleep(0.1)  # Give some time for the state transition
            
            # Get the current position when the motor is disabled - this is our "zero" reference point
            starting_position = self.odrive_controller.axis0.pos_vel_mapper.pos_rel
            self.update_terminal(f"Starting position (zero point): {starting_position} turns\n")
            
            # Both min and max angles should be treated as absolute values
            # Min angle is negative from current position, max angle is positive
            min_angle_degrees = float(self.min_angle_input.get())
            max_angle_degrees = float(self.max_angle_input.get())
            
            # Convert degrees to turns (corrected factor based on actual measurements)
            min_angle_turns = min_angle_degrees / 2.055  # Fine-tuned factor
            max_angle_turns = max_angle_degrees / 2.055  # Fine-tuned factor
            
            # Calculate absolute positions by adding to starting position
            # Min is negative from starting position, max is positive
            absolute_min_angle = starting_position - min_angle_turns  # Subtract for min angle
            absolute_max_angle = starting_position + max_angle_turns  # Add for max angle
            
            self.update_terminal(f"Min angle: -{min_angle_degrees} degrees from start ({absolute_min_angle} turns)\n")
            self.update_terminal(f"Max angle: +{max_angle_degrees} degrees from start ({absolute_max_angle} turns)\n")
            
            cycles = self.odrive_cycles
            self.update_terminal(f"Starting control cycle at {self.odrive_speed} deg/sec\n")
            
            # Convert degrees/second to turns/second using velocity-specific conversion factor
            velocity = self.odrive_speed / 2.455  # Velocity factor: 20°/s input → 23.9°/s actual
            
            # Set velocity limit
            self.odrive_controller.axis0.controller.config.vel_limit = velocity
            
            for i in range(cycles):
                # Move to minimum angle limit (negative direction from starting position)
                self.odrive_controller.axis0.controller.input_pos = absolute_min_angle
                self.update_terminal(f"Cycle {i+1}/{cycles}: Moving to Min Angle (-{min_angle_degrees} degrees)\n")
                while abs(self.odrive_controller.axis0.pos_vel_mapper.pos_rel - absolute_min_angle) > 0.01:
                    time.sleep(0.01)
                
                # Move to maximum angle limit (positive direction from starting position)
                self.odrive_controller.axis0.controller.input_pos = absolute_max_angle
                self.update_terminal(f"Cycle {i+1}/{cycles}: Moving to Max Angle (+{max_angle_degrees} degrees)\n")
                while abs(self.odrive_controller.axis0.pos_vel_mapper.pos_rel - absolute_max_angle) > 0.01:
                    time.sleep(0.01)
                
                if not self.odrive_ctrl:
                    break
            
            # Return to starting position (zero point) only after all cycles are complete
            self.odrive_controller.axis0.controller.input_pos = starting_position
            self.update_terminal("Returning to zero position (starting point)\n")
            
            # Wait for the motor to reach the zero position
            while abs(self.odrive_controller.axis0.pos_vel_mapper.pos_rel - starting_position) > 0.01:
                time.sleep(0.01)
            
            self.update_terminal("Successfully returned to zero position\n")
            time.sleep(1)
            
            # Set ODrive State to Idle
            self.odrive_controller.axis0.requested_state = AXIS_STATE_IDLE
            self.update_terminal("Odrive Idle State\n")
        except Exception as e:
            self.update_terminal(f"Error: {e}\n")

    def stop_logging(self):
        self.odrive_ctrl = False
        
        # Stop strain test if active
        if self.strain_test_active:
            self.stop_strain_test()
            self.update_terminal("Strain test stopped\n")
        
        # Return motor to starting position if connected and NOT in manual mode
        if self.odrive_controller and not self.manual_mode.get():
            try:
                # Return to starting position if we have one
                if hasattr(self, 'starting_position'):
                    self.update_terminal("Returning motor to starting position...\n")
                    self.odrive_controller.axis0.controller.input_pos = self.starting_position
                    
                    # Wait for the motor to reach the starting position
                    timeout_counter = 0
                    while abs(self.odrive_controller.axis0.pos_vel_mapper.pos_rel - self.starting_position) > 0.01:
                        time.sleep(0.01)
                        timeout_counter += 1
                        if timeout_counter > 500:  # 5 second timeout
                            self.update_terminal("Timeout waiting for motor to return to start position\n")
                            break
                    
                    self.update_terminal("Motor returned to starting position\n")
                
                # Set ODrive State to Idle
                self.odrive_controller.axis0.requested_state = AXIS_STATE_IDLE
                self.update_terminal("Motor disengaged and returned to idle state\n")
                
                # Disable manual control buttons and Start button
                self.left_arrow.configure(state="disabled")
                self.right_arrow.configure(state="disabled")
                self.step_angle_input.configure(state="disabled")
                self.mode_toggle.configure(state="disabled")
                self.buttons[1].configure(state="disabled")  # Disable Start button
                
            except Exception as e:
                self.update_terminal(f"Error during motor stop sequence: {e}\n")
        elif self.odrive_controller and self.manual_mode.get():
            # In manual mode, stop any continuous movement and disengage motor
            try:
                # Stop any continuous movement
                self.stop_continuous_movement()
                
                # Set ODrive State to Idle to disengage motor
                self.odrive_controller.axis0.requested_state = AXIS_STATE_IDLE
                self.update_terminal("Motor disengaged in manual mode\n")
                
                # Disable manual control buttons
                self.left_arrow.configure(state="disabled")
                self.right_arrow.configure(state="disabled")
                self.step_angle_input.configure(state="disabled")
                self.mode_toggle.configure(state="disabled")
                
            except Exception as e:
                self.update_terminal(f"Error during manual mode stop: {e}\n")

        # Stop any active logging
        if self.logging_active == True:
            self.logging_active = False
            
        # Always re-enable input fields when stopping
        self.live_update_flag = True
        self.speed_input.configure(state="normal")
        self.acceleration_input.configure(state="normal")
        self.min_angle_input.configure(state="normal")
        self.max_angle_input.configure(state="normal")
        self.cycles_input.configure(state="normal")
        self.file_name_input.configure(state="normal")
        
        self.update_terminal("All operations stopped and inputs re-enabled\n")
            


    def reset_display(self):
        self.live_update_flag = False  # Reset live update flag
        # Stop logging
        self.stop_logging()
        
        # Stop strain test if active
        if self.strain_test_active:
            self.stop_strain_test()
        
        # Clear terminal
        self.clear_terminal()

        self.live_update_flag = True  # Reset live update flag

        self.file_name_input.delete(0,100)
        self.cycles_input.delete(0,100)
        self.speed_input.delete(0,100)
        self.acceleration_input.delete(0,100)
        self.min_angle_input.delete(0,100)
        self.max_angle_input.delete(0,100)

        self.file_name_input.configure(placeholder_text="File Name (Prefix)")
        self.cycles_input.configure(placeholder_text="Cycles")
        self.speed_input.configure(placeholder_text="Speed (Degrees/S)")
        self.acceleration_input.configure(placeholder_text="Acceleration (Degrees/s^2)")
        self.min_angle_input.configure(placeholder_text="Min Angle (Degrees)")
        self.max_angle_input.configure(placeholder_text="Max Angle (Degrees)")

        self.file_name_input.configure(state= "normal")
        self.cycles_input.configure(state= "normal")
        self.speed_input.configure(state= "normal")
        self.acceleration_input.configure(state= "normal")
        self.min_angle_input.configure(state= "normal")
        self.max_angle_input.configure(state= "normal")
        self.file_name_input.configure(state="normal")
        
        # Disable Start button since we're resetting/disconnecting
        self.buttons[1].configure(state="disabled")  # Index 1 is the "Start" button
        
        # Disengage the motor if connected
        if self.odrive_controller:
            try:
                # Set ODrive State to Idle
                self.odrive_controller.axis0.requested_state = AXIS_STATE_IDLE
                self.update_terminal("Motor disengaged and returned to idle state\n")
            except Exception as e:
                self.update_terminal(f"Error disengaging motor: {e}\n")


    def clear_terminal(self):
        self.terminal.delete(1.0, ctk.END)
        self.terminal.update()


    def update_terminal(self, message):
        self.terminal.insert(ctk.END, message)
        self.terminal.see(ctk.END)  # Scroll to the end of the text

    def on_close(self):
        """Handle application closing"""
        # Calculate center position for the message box
        main_window_x = self.master.winfo_x()
        main_window_y = self.master.winfo_y()
        main_window_width = self.master.winfo_width()
        main_window_height = self.master.winfo_height()
        
        # Center coordinates
        center_x = main_window_x + (main_window_width // 2)
        center_y = main_window_y + (main_window_height // 2)
        
        msg = CTkMessagebox(
            title="Quit",
            message="Do you want to quit?",
            icon="question",
            option_1="Cancel",
            option_2="Yes",
            sound=True,
            button_hover_color="grey",  # Grey on hover
            button_width=120,  # Make buttons wider
            font=("Arial", 14),  # Larger font for text
            icon_size=(40, 40),  # Larger icon
            button_height=35,  # Taller buttons
            border_width=2,  # Add border for better visibility
            border_color="#444444",  # Dark grey border
            justify="center"  # Center the message text
        )
        
        # Position the message box (need to update after it's created)
        msg_width = 20  # Increased width for better button spacing
        msg_height = 200  # Approximate height of message box
        msg.geometry(f"+{center_x - msg_width//2}+{center_y - msg_height//2}")
        
        
        response = msg.get()
        
        if response == "Yes":
            try:
                # Stop any active processes first
                if self.strain_test_active:
                    self.stop_logging()
                
                # Close the plot window safely
                self.close_plot_window()
                
                # Disconnect from ODrive if connected
                if hasattr(self, 'odrive_controller') and self.odrive_controller:
                    try:
                        self.disconnect_odrive()
                    except:
                        pass  # Ignore any errors during ODrive disconnection
                
                # Disconnect from Phidget if connected
                if hasattr(self, 'voltage_ratio_input') and self.voltage_ratio_input:
                    try:
                        self.voltage_ratio_input.close()
                    except:
                        pass
                
                # Destroy the main window
                self.master.quit()
                self.master.destroy()
                
            except Exception as e:
                print(f"Error during shutdown: {e}")
                # Force quit if there's an error
                self.master.quit()
                self.master.destroy()

    def start_strain_test(self):
        """Start the strain test with the current motor settings"""
        # Clear plot data if plot window is open
        global angle_data, torque_data, plot_curve, plot_window
        if plot_window_open:
            angle_data = []
            torque_data = []
            if plot_curve is not None:
                plot_curve.setData(angle_data, torque_data)
                # Reset plot axes
                plot_window.setXRange(0, 1)  # Reset x-axis
                plot_window.setYRange(0, 1)  # Reset y-axis
                plot_window.enableAutoRange()  # Enable auto-ranging for both axes

        if not self.odrive_controller:
            self.update_terminal("No serial connection established. Please connect ODrive first.\n")
            return
        
        if self.strain_test_active:
            self.update_terminal("Strain test already active\n")
            return
        
        # Initialize Phidget
        try:
            self.voltage_ratio_input = VoltageRatioInput()
            self.voltage_ratio_input.setChannel(1)
            
            # Open and wait for attachment
            self.voltage_ratio_input.openWaitForAttachment(5000)
            
            # Configure settings after successful attachment
            self.voltage_ratio_input.setDataInterval(8)  # 8ms = 125Hz
            self.voltage_ratio_input.setDataRate(125)  # Set data rate to match interval
            
            # Tare the scale
            self.tare_scale()
            
            # Generate file name based on current date and time
            current_datetime = time.strftime("(%d-%m-%Y)_(%H-%M-%S)")
            folder_path = os.path.join(os.getcwd(), "OrthoSim Logs")
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
            self.strain_file_name = os.path.join(folder_path, f"{self.file_name_input.get()}_strain_data_{current_datetime}.csv")
            
            # Initialize CSV file with headers including raw and moving average columns
            with open(self.strain_file_name, mode="w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow([
                    "Timestamp", "Cycle", 
                    "Raw AFO Angle (Degrees)", "Moving Avg AFO Angle (Degrees)",
                    "Raw Weight (grams)", "Moving Avg Weight (grams)",
                    "Raw Torque (Nm)", "Moving Avg Torque (Nm)",
                    "Velocity (turns/s)", "Position (degrees)"
                ])
            
            # Initialize data buffer and plot update counter
            self.strain_data_buffer = []
            self.plot_update_counter = 0
            # self.plot_update_interval = 1  # Update plot every sample
            self.plot_update_interval = 5  # Update plot every 5 samples
            
            
            # Start the strain test thread
            self.strain_test_active = True
            self.strain_thread = threading.Thread(target=self.strain_test_control)
            self.strain_thread.start()
            
            # Start the data collection thread
            self.data_collection_thread = threading.Thread(target=self.continuous_strain_read)
            self.data_collection_thread.daemon = True
            self.data_collection_thread.start()
            
            self.update_terminal("Strain test started\n")
            
        except PhidgetException as e:
            self.update_terminal(f"Error initializing strain test: {str(e)}\n")
            self.strain_test_active = False
    


    def get_current_weight(self):
        """Get the current weight reading from the scale in grams"""
        if not calibrated:
            return 0.0
        voltage_ratio = self.voltage_ratio_input.getVoltageRatio()
        weight_newtons = (voltage_ratio - offset) * gain
        weight_grams = weight_newtons * newton_to_grams
        return weight_grams

    def tare_scale(self):
        """Tare the Phidget scale"""
        global offset, calibrated
        num_samples = 16
        
        self.update_terminal("Taring scale...\n")
        offset = 0  # Reset offset before taking new samples
        for _ in range(num_samples):
            offset += self.voltage_ratio_input.getVoltageRatio()
            time.sleep(self.voltage_ratio_input.getDataInterval() / 1000.0)
        
        offset /= num_samples
        calibrated = True
        self.update_terminal(f"Scale tared. Offset: {offset}\n")
        time.sleep(1)
        current_weight = self.get_current_weight()
        self.update_terminal(f"Current weight: {current_weight:.2f} grams\n")
        time.sleep(1)


    
    def log_strain_data(self, voltage_ratio, cycle):
        """Log strain data to buffer"""
        global calibrated, offset, gain, newton_to_grams
        
        try:
            if calibrated:
                current_time = time.time()
                
                # Get position data
                if hasattr(self, 'starting_position'):
                    current_pos_turns = self.odrive_controller.axis0.pos_vel_mapper.pos_rel
                    relative_angle = (current_pos_turns - self.starting_position) * 2.055  # Fine-tuned factor
                    velocity = self.odrive_controller.axis0.pos_vel_mapper.vel
                else:
                    relative_angle = 0
                    velocity = 0
                
                # Calculate raw weight
                raw_weight_newtons = (voltage_ratio - offset) * gain
                raw_weight_grams = raw_weight_newtons * newton_to_grams
                
                # Calculate raw torque using the provided formula
                distance_m = 0.4792  # Distance in meters
                force_n = raw_weight_grams * 9.81 / 1000  # Convert grams to kg, then to Newtons
                angle_component = (-0.0328 * (relative_angle**2)) - (1.0013 * relative_angle) + 90.272
                raw_torque_nm = force_n * distance_m * math.sin(math.radians(angle_component))
                
                # Apply moving average filter to angle, weight, and torque
                self.angle_filter.add_value(relative_angle)
                self.weight_filter.add_value(raw_weight_grams)
                self.torque_filter.add_value(raw_torque_nm)
                
                # Get smoothed values
                avg_angle = self.angle_filter.get_smoothed_value()
                avg_weight = self.weight_filter.get_smoothed_value()
                avg_torque = self.torque_filter.get_smoothed_value()
                
                # Check if we have valid smoothed values
                if avg_angle is None or avg_weight is None or avg_torque is None:
                    return
                
                # Check for duplicates (using averaged values)
                if (self.last_angle == avg_angle and 
                    self.last_weight == avg_weight):
                    return  # Skip this sample if it's a duplicate
                
                # Check if enough time has passed since the last logged sample
                if current_time - self.last_logged_time < self.min_time_between_samples:
                    return  # Skip this sample if it's too soon after the last one
                
                # Create timestamp with microsecond precision
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S") + ".{:03d}".format(int((current_time % 1) * 1000))
                
                # Add data row to buffer with both raw and moving average values
                # Order matches CSV headers:
                # "Timestamp", "Cycle", "Raw AFO Angle", "Moving Avg AFO Angle", "Raw Weight", "Moving Avg Weight", "Raw Torque", "Moving Avg Torque", "Velocity", "Position"
                data_row = [
                    timestamp,                    # Timestamp
                    self.current_cycle,           # Cycle
                    f"{relative_angle:.4f}",      # Raw AFO Angle
                    f"{avg_angle:.4f}",           # Moving Avg AFO Angle
                    f"{raw_weight_grams:.2f}",    # Raw Weight
                    f"{avg_weight:.2f}",          # Moving Avg Weight
                    f"{raw_torque_nm:.4f}",       # Raw Torque
                    f"{avg_torque:.4f}",          # Moving Avg Torque
                    f"{velocity:.2f}",            # Velocity
                    f"{avg_angle:.4f}"            # Position
                ]
                self.strain_data_buffer.append(data_row)
                
                # Update the last logged time and values
                self.last_logged_time = current_time
                self.last_angle = avg_angle
                self.last_weight = avg_weight
                
                # Write buffer to file if it reaches a certain size
                if len(self.strain_data_buffer) >= 100:
                    with open(self.strain_file_name, mode="a", newline="") as file:
                        writer = csv.writer(file)
                        writer.writerows(self.strain_data_buffer)
                    self.strain_data_buffer = []
                
                # Update plot data if plot window is open (using moving average values)
                if plot_window_open:
                    self.plot_update_counter += 1
                    if self.plot_update_counter >= self.plot_update_interval:
                        self.update_plot_data(relative_angle, avg_torque)  # Changed from weight to torque
                        # self.update_plot_data(avg_angle, avg_torque)  # Changed from weight to torque
                        self.plot_update_counter = 0
                
                # Update terminal less frequently (every 20th sample)
                if self.sample_count % 20 == 0:
                    self.update_terminal(f"Raw Weight: {raw_weight_grams:.2f} g, Avg Weight: {avg_weight:.2f} g\n")
                    self.update_terminal(f"Raw Angle: {relative_angle:.4f}°, Avg Angle: {avg_angle:.4f}°\n")
                    self.update_terminal(f"Raw Torque: {raw_torque_nm:.4f} Nm, Avg Torque: {avg_torque:.4f} Nm\n")
                
                self.sample_count += 1
                
            else:
                self.update_terminal("Phidget is not calibrated yet!\n")
                
        except Exception as e:
            self.update_terminal(f"Error logging strain data: {str(e)}\n")
    
    def strain_test_control(self):
        """Control the motor and log strain data during the test"""
        try:
            # Activate closed-loop control
            self.odrive_controller.axis0.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
            time.sleep(0.1)  # Give some time for the state transition
            
            # Get the current position when the motor is disabled - this is our "zero" reference point
            self.starting_position = self.odrive_controller.axis0.pos_vel_mapper.pos_rel
            self.update_terminal(f"Starting position (zero point): {self.starting_position} turns\n")
            
            # Both min and max angles should be treated as absolute values
            # Min angle is negative from current position, max angle is positive
            min_angle_degrees = float(self.min_angle_input.get())
            max_angle_degrees = float(self.max_angle_input.get())
            
            # Convert degrees to turns (corrected factor based on actual measurements)
            min_angle_turns = min_angle_degrees / 2.055  # Fine-tuned factor: 15°input → 14.905°actual
            max_angle_turns = max_angle_degrees / 2.055  # Fine-tuned factor: 15°input → 14.905°actual
            
            # Calculate absolute positions by adding to starting position
            # Min is negative from starting position, max angle is positive
            absolute_min_angle = self.starting_position - min_angle_turns  # Subtract for min angle
            absolute_max_angle = self.starting_position + max_angle_turns  # Add for max angle
            
            self.update_terminal(f"Min angle: -{min_angle_degrees} degrees from start ({absolute_min_angle} turns)\n")
            self.update_terminal(f"Max angle: +{max_angle_degrees} degrees from start ({absolute_max_angle} turns)\n")
            
            cycles = self.odrive_cycles
            self.update_terminal(f"Starting strain test at {self.odrive_speed} deg/sec\n")
            
            # Convert degrees/second to turns/second using velocity-specific conversion factor
            velocity = self.odrive_speed / 2.455  # Velocity factor: 20°/s input → 23.9°/s actual
            
            # Set velocity limit
            self.odrive_controller.axis0.controller.config.vel_limit = velocity
            
            # Start a thread to continuously read strain data
            strain_read_thread = threading.Thread(target=self.continuous_strain_read)
            strain_read_thread.daemon = True  # Make thread daemon so it exits when main thread exits
            strain_read_thread.start()
            
            # Initialize cycle tracking variables
            self.current_cycle = 0
            last_position = self.starting_position
            crossed_zero = False
            
            # Start at zero position
            self.odrive_controller.axis0.controller.input_pos = self.starting_position
            self.update_terminal("Starting at zero position\n")
            while abs(self.odrive_controller.axis0.pos_vel_mapper.pos_rel - self.starting_position) > 0.01:
                time.sleep(0.01)
            
            for i in range(cycles):
                # Move to maximum angle limit (positive direction from starting position)
                self.odrive_controller.axis0.controller.input_pos = absolute_max_angle
                self.update_terminal(f"Moving to Max Angle (+{max_angle_degrees} degrees)\n")
                while abs(self.odrive_controller.axis0.pos_vel_mapper.pos_rel - absolute_max_angle) > 0.01:
                    current_position = self.odrive_controller.axis0.pos_vel_mapper.pos_rel
                    # Check for zero crossing while moving towards max
                    if not crossed_zero and last_position < self.starting_position and current_position >= self.starting_position:
                        crossed_zero = True
                        self.current_cycle += 1
                        self.update_terminal(f"Completed cycle {self.current_cycle}/{cycles}\n")
                    last_position = current_position
                    time.sleep(0.01)
                
                # Move to minimum angle limit (negative direction from starting position)
                self.odrive_controller.axis0.controller.input_pos = absolute_min_angle
                self.update_terminal(f"Moving to Min Angle (-{min_angle_degrees} degrees)\n")
                while abs(self.odrive_controller.axis0.pos_vel_mapper.pos_rel - absolute_min_angle) > 0.01:
                    current_position = self.odrive_controller.axis0.pos_vel_mapper.pos_rel
                    # Check for zero crossing while moving towards min
                    if not crossed_zero and last_position > self.starting_position and current_position <= self.starting_position:
                        crossed_zero = True
                        self.current_cycle += 1
                        self.update_terminal(f"Completed cycle {self.current_cycle}/{cycles}\n")
                    last_position = current_position
                    time.sleep(0.01)
                
                # Reset the zero crossing flag for the next cycle
                crossed_zero = False
                
                if not self.strain_test_active:
                    break
            
            # Return to starting position (zero point) only after all cycles are complete
            self.odrive_controller.axis0.controller.input_pos = self.starting_position
            self.update_terminal("Returning to zero position (starting point)\n")
            
            # Wait for the motor to reach the zero position
            while abs(self.odrive_controller.axis0.pos_vel_mapper.pos_rel - self.starting_position) > 0.01:
                time.sleep(0.01)
            
            self.update_terminal("Successfully returned to zero position\n")
            time.sleep(1)
            
            # Stop the strain reading thread
            self.strain_test_active = False
            strain_read_thread.join(timeout=1.0)
            
            # Set ODrive State to Idle
            self.odrive_controller.axis0.requested_state = AXIS_STATE_IDLE
            self.update_terminal("Odrive Idle State\n")
            
            # Write all buffered data to the CSV file
            with open(self.strain_file_name, mode="a", newline="") as file:
                writer = csv.writer(file)
                writer.writerows(self.strain_data_buffer)
            
            self.update_terminal(f"Strain test completed. Data saved to {self.strain_file_name}\n")
            
        except Exception as e:
            self.update_terminal(f"Error during strain test: {e}\n")
        finally:
            self.strain_test_active = False
            try:
                self.voltage_ratio_input.close()
            except:
                pass
    
    def continuous_strain_read(self):
        """Continuously read strain data while the test is running"""
        try:
            while self.strain_test_active:
                voltage_ratio = self.voltage_ratio_input.getVoltageRatio()
                # Pass the current cycle number from the strain test control
                self.log_strain_data(voltage_ratio, self.current_cycle)
                time.sleep(0.008)  # 8ms delay for 125Hz data rate
                
        except Exception as e:
            self.update_terminal(f"Error reading strain data: {e}\n")
        finally:
            # Write any remaining data in buffer
            if self.strain_data_buffer:
                with open(self.strain_file_name, mode="a", newline="") as file:
                    writer = csv.writer(file)
                    writer.writerows(self.strain_data_buffer)
                self.strain_data_buffer = []

    def stop_strain_test(self):
        """Stop the strain test"""
        if self.strain_test_active:
            self.strain_test_active = False
            self.update_terminal("Stopping strain test...\n")
        else:
            self.update_terminal("No strain test active\n")

    def create_plot_window(self):
        """Create a plot window that stays on top of the main window"""
        global plot_window_open, plot_window, plot_curve, angle_data, weight_data
        
        try:
            # Reset data arrays
            angle_data = []
            torque_data = []
            
            # Get title from file name prefix field
            plot_title = self.file_name_input.get() or "AFO Strain Test"
            
            # Create plot window if not already open
            if not plot_window_open:
                # Configure PyQtGraph appearance
                pg.setConfigOption('background', '#2b2b2b')  # Dark gray background
                pg.setConfigOption('foreground', 'w')  # White text and lines
                pg.setConfigOptions(antialias=True)  # Enable antialiasing globally
                
                # Create a QWidget container first
                self.plot_container = QWidget()
                
                # Set fixed size
                self.plot_container.setFixedSize(750, 550)
                
                # Set rounded corners using stylesheet
                self.plot_container.setStyleSheet("""
                    QWidget {
                        background-color: #2b2b2b;
                        border: 0px solid #444444;
                    }
                """)
                
                # Create the plot widget with no navigation bar
                plot_window = pg.PlotWidget()
                plot_window.setBackground('#2b2b2b')
                
                # Enable antialiasing for the plot
                plot_window.setAntialiasing(True)
                
                # Set title with larger font
                title_style = {'color': '#ffffff', 'size': '18pt'}
                plot_window.setTitle(plot_title, **title_style)
                
                # Set axis labels with larger font and white color
                label_style = {'color': '#ffffff', 'font-size': '12pt'}
                plot_window.setLabel('left', 'Torque (Nm)', **label_style)
                plot_window.setLabel('bottom', 'AFO Angle (degrees)', **label_style)
                
                # Hide the navigation bar
                plot_window.hideButtons()
                
                # Set grid style
                plot_window.showGrid(x=True, y=True, alpha=0.3)
                
                # Customize axes with larger text
                for axis in [plot_window.getAxis('left'), plot_window.getAxis('bottom')]:
                    axis.setPen(color='white', width=2)
                    axis.setTextPen(color='white')
                    axis.setStyle(tickFont=QFont('Arial', 12))
                    # Make the axis numbers white
                    axis.setTextPen('w')
                
                # Add a legend with custom styling and larger text
                legend = plot_window.addLegend(pen='w', brush=(50, 50, 50, 200), labelTextColor='w')
                legend.setLabelTextSize('12pt')  # Increased legend text size
                
                # Create the data curve with line only (no symbols)
                plot_curve = plot_window.plot(
                    angle_data, 
                    torque_data, 
                    pen=pg.mkPen(
                        color=(255, 215, 0),  # Gold color
                        width=2,  # Maintain line width for clarity
                        cosmetic=True,  # Ensures consistent width during scaling
                        style=Qt.SolidLine  # Ensure solid line style
                    ),
                    name='Torque vs Angle',
                    antialias=True,  # Enable antialiasing for the curve
                    connect='all',  # Connect all points for smoother line
                    skipFiniteCheck=True  # Skip finite check for better performance
                )
                
                # Create layout and add plot widget to container
                layout = QVBoxLayout(self.plot_container)
                layout.setContentsMargins(15, 15, 15, 15)  # Add more padding around the plot
                layout.addWidget(plot_window)
                
                # Position the window relative to the main window
                self.plot_container.move(self.master.winfo_x() + 450, self.master.winfo_y() + 190)
                
                # Set window flags for a child window that stays on top of main window
                self.plot_container.setWindowFlags(
                    Qt.Tool |  # Makes it a tool window that stays on top of its parent
                    Qt.CustomizeWindowHint |  # Keeps custom window appearance
                    Qt.FramelessWindowHint  # Removes the window frame
                )
                
                # Show the container
                self.plot_container.show()
                self.plot_container.raise_()  # Ensure it's on top
                
                # Apply rounded corners to the actual window using win32 API
                try:
                    import win32gui
                    import win32con
                    from ctypes import windll, c_int, byref
                    
                    # Get the window handle
                    hwnd = self.plot_container.winId().__int__()
                    
                    # Define the region
                    region = win32gui.CreateRoundRectRgn(0, 0, 750, 550, 40, 40)
                    
                    # Set the window region
                    win32gui.SetWindowRgn(hwnd, region, True)
                    
                    # Make sure the window is layered for transparency
                    style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style | win32con.WS_EX_LAYERED)
                    
                    # Set the window transparency
                    windll.user32.SetLayeredWindowAttributes(hwnd, 0, 255, win32con.LWA_ALPHA)
                except Exception as e:
                    print(f"Error applying rounded corners: {e}")
                
                # Set up a timer for plot updates
                self.setup_plot_timer()
                
                plot_window_open = True
                self.update_terminal("Plot window created successfully\n")
            
            # Update title if plot already exists
            else:
                plot_window.setTitle(plot_title)
                self.plot_container.raise_()  # Ensure window is on top when updating
                self.update_terminal("Plot updated\n")
                
        except Exception as e:
            self.update_terminal(f"Error creating plot window: {str(e)}\n")
            plot_window_open = False

    def setup_plot_timer(self):
        """Set up a timer to update the plot periodically"""
        global plot_timer
        
        # Create a timer for updating the plot
        plot_timer = QTimer()
        plot_timer.timeout.connect(self.update_plot)
        plot_timer.start(8)  # Update plot every 8ms (125Hz) to match data collection rate
    
    def update_plot(self):
        """Update the plot with new data"""
        global plot_curve, angle_data, torque_data, plot_window_open
        
        # Check if plot window is still open
        if not plot_window_open:
            return
        
        # Update plot with new data if available
        if angle_data and torque_data:
            plot_curve.setData(angle_data, torque_data)
    
    def close_plot_window(self):
        """Close the plot window safely"""
        global plot_window_open, plot_window, plot_curve, angle_data, torque_data
        
        try:
            if hasattr(self, 'plot_container') and self.plot_container is not None:
                # Hide the container first
                self.plot_container.hide()
                
                # Clear the plot data
                if plot_curve is not None:
                    plot_curve.clear()
                angle_data = []
                torque_data = []
                
                # Delete the plot curve reference
                plot_curve = None
                
                # Close and delete the plot window
                if plot_window is not None:
                    plot_window.setParent(None)
                    plot_window = None
                
                # Close and delete the container
                self.plot_container.setParent(None)
                self.plot_container.deleteLater()
                self.plot_container = None
                
                plot_window_open = False
        except Exception as e:
            print(f"Error closing plot window: {e}")
            # Ensure flags are reset even if there's an error
            plot_window_open = False
            plot_window = None
            plot_curve = None
            self.plot_container = None

    def update_plot_data(self, angle, torque):
        """Add new data points to the plot"""
        global angle_data, torque_data, plot_window_open, plot_curve
        
        try:
            # Only update if plot window is open
            if plot_window_open and plot_curve is not None:
                # Add new data points
                angle_data.append(angle)  # Use the moving average values directly
                torque_data.append(torque)  # Use the moving average values directly
                
                # Keep a maximum number of points for performance
                max_points = 10000  # Keep high number of points for resolution
                if len(angle_data) > max_points:
                    # Keep more recent points for better resolution
                    angle_data = angle_data[-max_points:]
                    torque_data = torque_data[-max_points:]
                
                # Update the plot with the data
                plot_curve.setData(
                    angle_data, 
                    torque_data,
                    connect='all',  # Connect all points for smoother line
                    skipFiniteCheck=True  # Skip finite check for better performance
                )
                
                # Auto-scale the plot to show all data points
                plot_window.enableAutoRange()
        except Exception as e:
            self.update_terminal(f"Error updating plot: {str(e)}\n")

    def validate_step_angle(self, event=None):
        """Validate and constrain step angle input"""
        try:
            value = self.step_angle_input.get()
            if value:  # Only validate if there's a value
                angle = float(value)
                if angle < 0:
                    self.step_angle_input.delete(0, 'end')
                    self.step_angle_input.insert(0, "0")
                    self.update_terminal("Step angle must be at least 0.01 degrees\n")
                elif angle > 10:
                    self.step_angle_input.delete(0, 'end')
                    self.step_angle_input.insert(0, "10")
                    self.update_terminal("Step angle cannot exceed 10 degrees\n")
        except ValueError:
            # If the input is not a valid number, clear it
            self.step_angle_input.delete(0, 'end')

    def move_motor_left(self):
        """Move the motor to the left (negative direction)"""
        if not hasattr(self, 'odrive_controller') or not self.odrive_controller:
            self.update_terminal("ODrive not connected\n")
            return
            
        try:
            current_pos = self.odrive_controller.axis0.pos_vel_mapper.pos_rel
            
            if self.continuous_mode.get():
                # Start continuous movement
                self.continuous_movement_active = True
                self.movement_direction = "left"
                self.start_continuous_movement()
            else:
                # In step mode, move by the specified angle
                try:
                    step_angle = float(self.step_angle_input.get())
                    # Constrain step angle between 0.01 and 5 degrees
                    step_angle = max(0.01, min(10.0, step_angle))
                    # Convert degrees to turns (corrected factor)
                    step_turns = step_angle / 2.055  # Fine-tuned factor
                    target_pos = current_pos - step_turns
                    self.odrive_controller.axis0.controller.input_pos = target_pos
                    self.update_terminal(f"Moved left by {step_angle:.2f} degrees\n")
                except ValueError:
                    self.update_terminal("Please enter a valid step angle between 0 and 10 degrees\n")
                    
        except Exception as e:
            self.update_terminal(f"Error moving motor: {e}\n")

    def move_motor_right(self):
        """Move the motor to the right (positive direction)"""
        if not hasattr(self, 'odrive_controller') or not self.odrive_controller:
            self.update_terminal("ODrive not connected\n")
            return
            
        try:
            current_pos = self.odrive_controller.axis0.pos_vel_mapper.pos_rel
            
            if self.continuous_mode.get():
                # Start continuous movement
                self.continuous_movement_active = True
                self.movement_direction = "right"
                self.start_continuous_movement()
            else:
                # In step mode, move by the specified angle
                try:
                    step_angle = float(self.step_angle_input.get())
                    # Constrain step angle between 0.01 and 5 degrees
                    step_angle = max(0.01, min(10.0, step_angle))
                    # Convert degrees to turns (corrected factor)
                    step_turns = step_angle / 2.055  # Fine-tuned factor
                    target_pos = current_pos + step_turns
                    self.odrive_controller.axis0.controller.input_pos = target_pos
                    self.update_terminal(f"Moved right by {step_angle:.2f} degrees\n")
                except ValueError:
                    self.update_terminal("Please enter a valid step angle between 0 and 10 degrees\n")
                    
        except Exception as e:
            self.update_terminal(f"Error moving motor: {e}\n")

    def start_continuous_movement(self):
        """Start continuous movement in the current direction"""
        if not self.continuous_movement_active:
            return

        try:
            current_pos = self.odrive_controller.axis0.pos_vel_mapper.pos_rel
            increment = 0.1  # Small increment for smooth movement
            
            if self.movement_direction == "left":
                target_pos = current_pos - increment
            else:  # right
                target_pos = current_pos + increment
                
            self.odrive_controller.axis0.controller.input_pos = target_pos
            
            # Schedule the next movement
            self.movement_timer = self.master.after(50, self.start_continuous_movement)  # 50ms = 20Hz update rate
            
        except Exception as e:
            self.update_terminal(f"Error in continuous movement: {e}\n")
            self.stop_continuous_movement()

    def stop_continuous_movement(self):
        """Stop continuous movement"""
        self.continuous_movement_active = False
        if self.movement_timer:
            self.master.after_cancel(self.movement_timer)
            self.movement_timer = None

    def toggle_manual_mode(self):
        """Handle manual mode toggle"""
        if self.manual_mode.get():
            # Enable manual controls
            self.left_arrow.configure(state="normal")
            self.right_arrow.configure(state="normal")
            self.step_angle_input.configure(state="normal")
            self.mode_toggle.configure(state="normal")
            
            # Disable Start button in manual mode
            self.buttons[1].configure(state="disabled")
            
            # Disable input fields
            self.speed_input.configure(state="disabled")
            self.acceleration_input.configure(state="disabled")
            self.min_angle_input.configure(state="disabled")
            self.max_angle_input.configure(state="disabled")
            self.cycles_input.configure(state="disabled")
        else:
            # Disable manual controls
            self.left_arrow.configure(state="disabled")
            self.right_arrow.configure(state="disabled")
            self.step_angle_input.configure(state="disabled")
            self.mode_toggle.configure(state="disabled")
            
            # Enable Start button when not in manual mode (only if connected)
            if hasattr(self, 'odrive_controller') and self.odrive_controller:
                self.buttons[1].configure(state="normal")
            
            # Enable input fields
            self.speed_input.configure(state="normal")
            self.acceleration_input.configure(state="normal")
            self.min_angle_input.configure(state="normal")
            self.max_angle_input.configure(state="normal")
            self.cycles_input.configure(state="normal")

    def validate_angle_input(self, event=None):
        """Validate and constrain angle inputs to 12 degrees"""
        try:
            # Get the widget that triggered the event
            widget = event.widget
            
            # Get the current value
            value = widget.get()
            if value:  # Only validate if there's a value
                angle = float(value)
                if angle > 12:
                    widget.delete(0, 'end')
                    widget.insert(0, "12")
                    self.update_terminal("Angle cannot exceed 12 degrees\n")
                elif angle < -12:
                    widget.delete(0, 'end')
                    widget.insert(0, "-12")
                    self.update_terminal("Angle cannot be less than -12 degrees\n")
        except ValueError:
            # If the input is not a valid number, clear it
            widget.delete(0, 'end')

def create_about_dialog(root):
    cur_dir = os.getcwd()
    cur_dir = cur_dir.replace("\\", "/")
    # icon_path = cur_dir+"/favicon.ico"
    icon_path = "images/icon.ico"

    # Set the icon for the about dialog
    about_dialog = ctk.CTk()
    
    about_dialog.geometry("560x775")  # Adjust dimensions as needed
    about_dialog.title("About")
    about_dialog.attributes("-topmost", True)  # Set the window to be topmost
    about_dialog.iconbitmap(icon_path)  # Set the icon for the about dialog

    # Frame for content
    content_frame = ctk.CTkFrame(master=about_dialog, width=2000, height=200)
    content_frame.pack(padx=25, pady=25)

    # Application name label (customize text and font)
    app_name_label = ctk.CTkLabel(master=content_frame,
                                text="OrthoSim",
                                font=("Arial", 18, "bold"))
    app_name_label.pack(pady=10)

    # Version label (customize text and font)
    version_label = ctk.CTkLabel(master=content_frame,
                                text="Version: 1.0",  # Update version number
                                font=("Arial", 12, "bold"))
    version_label.pack()

    # Author label (customize text and font)
    author_label = ctk.CTkLabel(master=content_frame,
                                text="Developed by: Brock Cooper",
                                font=("Arial", 12, "bold"))
    author_label.pack()

    # Usage
    description_label = ctk.CTkLabel(master=content_frame,
                                text="\n\
This program was designed specifically to be used with the custom AFO tester.\n\n\
The program will display the current angle and weight of the AFO on the plot window.\n\n\
The program will also display the current cycle number and the total cycles in the strain test.\n\n\
In order to start logging data fill in all the fields and click the connect button.\n\n\
The program will connect to the AFO tester and display if the connection is successful.\n\n\
To start a test click the start button and the program will begin logging data.\n\n\
You should see the terminal window start to display the data as the program is logging.\n\n\
The weight and angle values update on the plot window.",
                                font=("Arial", 12), padx=20)
    description_label.pack()


    # Copyright label (customize text and font)
    copyright_label = ctk.CTkLabel(master=content_frame,
                                text="Copyright © 2024 Brock Cooper",
                                font=("Arial", 10))
    copyright_label.pack()

    # Close button
    close_button = ctk.CTkButton(master=content_frame,
                                text="Close",
                                command=about_dialog.destroy)
    close_button.pack(pady=20)


    about_dialog.mainloop()

def main():
    # Ensure there's only one QApplication instance
    if not QApplication.instance():
        app = QApplication(sys.argv)
    else:
        app = QApplication.instance()
    
    root = ctk.CTk()
    root.geometry("1242x786")
    root.resizable(False, False)

    app_instance = MyInterface(root)
    root.protocol("WM_DELETE_WINDOW", app_instance.on_close)

    # Set the window icon
    try:
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images", "icon.ico")
        if os.path.exists(icon_path):
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(icon_path)
            root.iconbitmap(icon_path)
    except Exception as e:
        print(f"Failed to set icon: {e}")

    # Create menubar
    menubar = tk.Menu(root)
    file_menu = tk.Menu(menubar, tearoff=0)
    menubar.add_cascade(label="File", menu=file_menu)
    file_menu.add_command(label="Help", command=lambda: create_about_dialog(root))
    root.configure(menu=menubar)
    
    # Create plot window with delay
    root.after(500, app_instance.create_plot_window)
    root.update_idletasks()
    
    root.mainloop()
    
    # Cleanup Qt application
    if QApplication.instance():
        QApplication.instance().quit()

if __name__ == "__main__":
    main()