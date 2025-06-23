import csv
import time
from Phidget22.Phidget import *
from Phidget22.Devices.VoltageRatioInput import *

# Insert your gain value from the Phidget Control Panel
gain = -8133.8  # Example value

# The offset is calculated in tareScale
offset = 0

# Convert from Newtons to grams (1 Newton = 100 grams)
newton_to_grams = 1000

# Calibration flag
calibrated = False

# CSV file path
csv_file = "weight_readings.csv"

# Function to log weight to a CSV file
def log_weight_to_csv(weight_grams):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")  # Current timestamp
    with open(csv_file, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([timestamp, weight_grams])
    print(f"Logged to CSV: {timestamp}, {weight_grams} grams")

# This function is called whenever the voltage ratio changes
def onVoltageRatioChange(self, voltageRatio):
    if calibrated:
        # Apply the calibration parameters (gain, offset) to the raw voltage ratio
        weight_newtons = (voltageRatio - offset) * gain        
        weight_grams = weight_newtons * newton_to_grams  # Convert from Newtons to grams
        print("Weight (grams): " + str(weight_grams))
        log_weight_to_csv(weight_grams)  # Log the value to the CSV

# This function tars (zeroes) the scale by averaging readings
def tareScale(ch):    
    global offset, calibrated
    num_samples = 16

    for i in range(num_samples):
        offset += ch.getVoltageRatio()
        time.sleep(ch.getDataInterval()/1000.0)
        
    offset /= num_samples
    print(offset)
    calibrated = True    

# Main function to setup and run the program
def main():
    # Create or overwrite the CSV file with a header row
    with open(csv_file, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Timestamp", "Weight (grams)"])

    voltageRatioInput1 = VoltageRatioInput()

    # Set the channel you want to read from (channel 1 in this case)
    voltageRatioInput1.setChannel(1)  # Set to channel 1
    
    # If you know the serial number of the device, you can set it directly
    # voltageRatioInput1.setDeviceSerialNumber(your_device_serial_number)  # Uncomment and set the serial number
    
    voltageRatioInput1.setOnVoltageRatioChangeHandler(onVoltageRatioChange)
    voltageRatioInput1.openWaitForAttachment(5000)
    
    # Set the data interval for the application (in milliseconds)
    voltageRatioInput1.setDataInterval(50)
    
    print("Taring")
    
    # Start the tare process
    tareScale(voltageRatioInput1)
    
    print("Taring Complete")
        
    try:
        input("Press Enter to Stop\n")
    except (Exception, KeyboardInterrupt):
        pass

    voltageRatioInput1.close()

# Run the main function
main()
