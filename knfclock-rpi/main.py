import RPi.GPIO as GPIO
import time
from datetime import datetime, timedelta
from astral import LocationInfo
from astral.sun import sun as astral_sun
import requests
import json
import os
import serial
from zoneinfo import ZoneInfo



# Environment variables
CONTROLLER_CONFIG_FILENAME = os.getenv('CONTROLLER_CONFIG_FILENAME')
CONTROLLER_KNFCLOCK_API_URL = os.getenv('CONTROLLER_KNFCLOCK_API_URL')
KNFCLOCK_REFRESH_TIME = int(os.getenv('KNFCLOCK_REFRESH_TIME', 30))




# GPIO Outputs
#          0,  1, 2,  3,  4,  5,  6,  7,  8,  9, 10, 11
outputs = [2,  3, 4, 14, 15, 17, 18, 27, 22, 23, 24, 10]
borderLamps = 19



# Setup GPIO
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(outputs, GPIO.OUT)
GPIO.setup(borderLamps, GPIO.OUT)





def addMinutes(tm, mins):
    fulldate = datetime(100, 1, 1, tm.hour, tm.minute, tm.second)
    fulldate = fulldate + timedelta(minutes=mins)
    return fulldate.time()



def show_time_v1():
	
	# Load Tracer Configuration
	dataForTracer = {}
	Tracer_TurnOnOffset = 0
	Tracer_TurnOffOffset = 0
	IsSystemTurnedOn = 0
	DoNotLookAtSunriseTime = 0
	if(os.path.exists(CONTROLLER_CONFIG_FILENAME)):
		with open(CONTROLLER_CONFIG_FILENAME) as json_file:
			data = json.load(json_file)
			if('TurnOffOffset' in data):
				TurnOffOffset = data['TurnOffOffset']
			if('TurnOnOffset' in data):
				TurnOnOffset = data['TurnOnOffset']
			if('IsSystemTurnedOn' in data):
				IsSystemTurnedOn = data['IsSystemTurnedOn']
			if('DoNotLookAtSunriseTime' in data):
				DoNotLookAtSunriseTime = data['DoNotLookAtSunriseTime']

	serialSession = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
	serialSession.reset_input_buffer()
	oldPowerUsage = ''
	while True:
		hour = datetime.now().hour
		timeNow = datetime.now().strftime("%H:%M:%S")


		city = LocationInfo("Vilnius", "Lithuania", "Europe/Vilnius", 54.687157, 25.279652)
		tz = ZoneInfo("Europe/Vilnius")  # Define tz here
		sun = astral_sun(city.observer, date=datetime.now().date(), tzinfo=tz)
		TodayTurnOffTime = (addMinutes(sun['sunrise'].time(), Tracer_TurnOffOffset)).strftime("%H:%M:%S")
		TodayTurnOnTime = (addMinutes(sun['sunset'].time(), Tracer_TurnOnOffset)).strftime("%H:%M:%S")

		# To Tracer System
		dataForTracer['SunSetTime'] = str(sun['sunset'].time())
		dataForTracer['SunRiseTime'] = str(sun['sunrise'].time())
		dataForTracer['TodayTurnOnTime'] = TodayTurnOnTime
		dataForTracer['TodayTurnOffTime'] = TodayTurnOffTime

		if(DoNotLookAtSunriseTime == 1):
			TodayTurnOnTime = "00:00:00"
			TodayTurnOffTime = "24:00:00"

		if((timeNow<=TodayTurnOffTime or timeNow>=TodayTurnOnTime) and IsSystemTurnedOn > 0):
			GPIO.output(borderLamps, GPIO.HIGH)
			dataForTracer['CurrentlyON'] = True

			if hour > 12:
				hour = hour - 12 - 1
			elif hour > 0:
				hour = hour - 1
			else:
				hour = 11

			for output in outputs:
				GPIO.output(output, GPIO.LOW)

			if(IsSystemTurnedOn == 2):
				GPIO.output(outputs[hour], GPIO.HIGH)
				dataForTracer['CurrentlyONLamp'] = hour + 1
				#print("Lamp (0..11): " + str(hour) )
			else:
				dataForTracer['CurrentlyONLamp'] = 0
				#print("Only Borders")



		else:
			GPIO.output(borderLamps, GPIO.LOW)
			for output in outputs:
				GPIO.output(output, GPIO.LOW)
			print("Turned OFF. TodayTurnOffTime: " + TodayTurnOffTime + " TodayTurnOnTime: " + TodayTurnOnTime)

			# To Tracer System
			dataForTracer['CurrentlyON'] = False
			dataForTracer['CurrentlyONLamp'] = 0



		dataForTracer.pop('powerUsage', None)
		if serialSession.in_waiting > 0:
			serialSession.reset_input_buffer()
			line = serialSession.readline().decode('utf-8').rstrip()
			if(line!=oldPowerUsage):
				oldPowerUsage = line
				dataForTracer['powerUsage'] = line

		# Send To And Get Back From Tracer System
		# SEND HERE
		try:
			print(json.dumps(dataForTracer, indent=4, sort_keys=True)) # Debug
			responseJson = requests.post(CONTROLLER_KNFCLOCK_API_URL, json=dataForTracer).json()
			with open(CONTROLLER_CONFIG_FILENAME, 'w') as outfile:
				json.dump(responseJson, outfile)

			IsSystemTurnedOn = responseJson['IsSystemTurnedOn']
			#print(json.dumps(responseJson, indent=4, sort_keys=True)) # Debug
		except:
			pass


		time.sleep(KNFCLOCK_REFRESH_TIME)








if __name__ == '__main__':
	show_time_v1()

