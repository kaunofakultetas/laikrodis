############################################################
#  [*] KNF clock controller — facade clock lighting driver
#
#  Runs on the Raspberry Pi inside the faculty facade clock
#  (the laikrodis stack): drives the twelve hour lamps and
#  the contour ("border") lamps by sunrise/sunset, reports
#  its state to Tracer's knfclock bridge every
#  KNFCLOCK_REFRESH_TIME seconds and applies the four
#  control parameters the answer carries — the values saved
#  on Tracer's KNF Clock page. Tracer being unreachable
#  never stops the clock: the loop keeps running on the
#  last known controls, and the last answer is cached in a
#  config file so even a restart starts from them.
#
#  Used by:
#    - docker-compose (knfclock-rpi service) — runs this as
#      the container entrypoint
#    - backend/app/bridges/knfclock.py — the Tracer side of
#      the exchange
############################################################


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








############################################################
# Environment variables
############################################################
#
# CONTROLLER_CONFIG_FILENAME — where every Tracer answer is
# cached so a restart starts from the last known controls;
# CONTROLLER_KNFCLOCK_API_URL + KNFCLOCK_BRIDGE_API_KEY —
# the knfclock bridge endpoint and its X-API-Key;
# KNFCLOCK_REFRESH_TIME — seconds between check-ins.
############################################################

CONTROLLER_CONFIG_FILENAME = os.getenv('CONTROLLER_CONFIG_FILENAME')
CONTROLLER_KNFCLOCK_API_URL = os.getenv('CONTROLLER_KNFCLOCK_API_URL')
KNFCLOCK_REFRESH_TIME = int(os.getenv('KNFCLOCK_REFRESH_TIME', 30))
KNFCLOCK_BRIDGE_API_KEY = os.getenv('KNFCLOCK_BRIDGE_API_KEY', '')








############################################################
# GPIO outputs
############################################################
#
# outputs[i] is the BCM pin of hour lamp i — index 0 is the
# 1 o'clock lamp, index 11 the 12 o'clock one (the index
# ruler below the banner). borderLamps drives the contour
# lighting relay.
############################################################

#          0,  1, 2,  3,  4,  5,  6,  7,  8,  9, 10, 11
outputs = [2,  3, 4, 14, 15, 17, 18, 27, 22, 23, 24, 10]
borderLamps = 19








############################################################
# GPIO setup
############################################################
#
# BCM numbering, warnings off (a container restart finds
# the pins still claimed), every lamp pin an output.
############################################################

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(outputs, GPIO.OUT)
GPIO.setup(borderLamps, GPIO.OUT)








############################################################
# addMinutes
############################################################
#
# A time-of-day plus minutes (negative allowed), wrapping
# through midnight — the dummy year-100 date exists only to
# borrow datetime's arithmetic for a bare time.
#
# Used by:
#   - show_time_v1 (below) — the turn-on/turn-off schedule
############################################################

def addMinutes(tm, mins):
    fulldate = datetime(100, 1, 1, tm.hour, tm.minute, tm.second)
    fulldate = fulldate + timedelta(minutes=mins)
    return fulldate.time()








############################################################
# show_time_v1
############################################################
#
# The controller loop: each cycle recomputes today's
# sunrise/sunset for Vilnius, decides whether the lamps are
# inside their ON window, drives the GPIO relays, ships the
# state (plus power-meter readings from the serial line) to
# Tracer's knfclock bridge and applies the four control
# values the answer carries.
#
# Used by:
#   - __main__ (below)
############################################################

def show_time_v1():
	# STEP 1: start from the last cached Tracer answer — the
	# controls survive a restart with Tracer unreachable.
	# (Fixed 2026-08: the offsets used to load into
	# TurnOffOffset / TurnOnOffset, which nothing reads — the
	# Tracer_ variables the loop uses stayed 0 forever)
	# ======================================================
	dataForTracer = {}
	Tracer_TurnOnOffset = 0
	Tracer_TurnOffOffset = 0
	IsSystemTurnedOn = 0
	DoNotLookAtSunriseTime = 0
	if(os.path.exists(CONTROLLER_CONFIG_FILENAME)):
		with open(CONTROLLER_CONFIG_FILENAME) as json_file:
			data = json.load(json_file)
			if('TurnOffOffset' in data):
				Tracer_TurnOffOffset = data['TurnOffOffset']
			if('TurnOnOffset' in data):
				Tracer_TurnOnOffset = data['TurnOnOffset']
			if('IsSystemTurnedOn' in data):
				IsSystemTurnedOn = data['IsSystemTurnedOn']
			if('DoNotLookAtSunriseTime' in data):
				DoNotLookAtSunriseTime = data['DoNotLookAtSunriseTime']


	# STEP 2: the power meter on the serial line — only
	# CHANGED readings are shipped, so oldPowerUsage tracks
	# the last one sent
	# =====================================================
	serialSession = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
	serialSession.reset_input_buffer()
	oldPowerUsage = ''
	while True:
		# STEP 3: the wall clock and today's sun times for
		# Vilnius; the offsets (minutes, from Tracer) shape the
		# lamp schedule, and the raw sun/schedule times are
		# what gets reported
		# ====================================================
		hour = datetime.now().hour
		timeNow = datetime.now().strftime("%H:%M:%S")


		city = LocationInfo("Vilnius", "Lithuania", "Europe/Vilnius", 54.687157, 25.279652)
		tz = ZoneInfo("Europe/Vilnius")
		sun = astral_sun(city.observer, date=datetime.now().date(), tzinfo=tz)
		TodayTurnOffTime = (addMinutes(sun['sunrise'].time(), Tracer_TurnOffOffset)).strftime("%H:%M:%S")
		TodayTurnOnTime = (addMinutes(sun['sunset'].time(), Tracer_TurnOnOffset)).strftime("%H:%M:%S")

		dataForTracer['SunSetTime'] = str(sun['sunset'].time())
		dataForTracer['SunRiseTime'] = str(sun['sunrise'].time())
		dataForTracer['TodayTurnOnTime'] = TodayTurnOnTime
		dataForTracer['TodayTurnOffTime'] = TodayTurnOffTime


		# STEP 4: the ON window — "HH:MM:SS" string comparison,
		# spanning the night from turn-on (sunset side) to
		# turn-off (sunrise side). Sun mode 1 forces bounds the
		# test always satisfies: always on, sun ignored.
		# (Tracer is told the REAL schedule either way)
		# =====================================================
		if(DoNotLookAtSunriseTime == 1):
			TodayTurnOnTime = "00:00:00"
			TodayTurnOffTime = "24:00:00"

		if((timeNow<=TodayTurnOffTime or timeNow>=TodayTurnOnTime) and IsSystemTurnedOn > 0):
			# STEP 4.1: inside the window — contours on, and in mode 2 the current hour's lamp too
			GPIO.output(borderLamps, GPIO.HIGH)
			dataForTracer['CurrentlyON'] = True

			# Wall-clock hour to lamp index: 0 is the 1 o'clock
			# lamp, 11 the 12 o'clock one
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
			# STEP 4.2: outside the window (or system off) — everything dark
			GPIO.output(borderLamps, GPIO.LOW)
			for output in outputs:
				GPIO.output(output, GPIO.LOW)
			print("Turned OFF. TodayTurnOffTime: " + TodayTurnOffTime + " TodayTurnOnTime: " + TodayTurnOnTime)

			dataForTracer['CurrentlyON'] = False
			dataForTracer['CurrentlyONLamp'] = 0


		# STEP 5: a fresh power-meter reading, shipped only
		# when it CHANGED — the stale one is popped first so an
		# unchanged value is not re-sent every cycle
		# ====================================================
		dataForTracer.pop('powerUsage', None)
		if serialSession.in_waiting > 0:
			serialSession.reset_input_buffer()
			line = serialSession.readline().decode('utf-8').rstrip()
			if(line!=oldPowerUsage):
				oldPowerUsage = line
				dataForTracer['powerUsage'] = line


		# STEP 6: ship the state to Tracer, cache the answer
		# for the next restart and apply all four control
		# values LIVE (2026-08: only IsSystemTurnedOn did;
		# offsets and the sun mode needed a restart — or, for
		# the offsets, never applied at all). .get keeps the
		# current value if a key is ever missing; a failed
		# POST is swallowed — an offline Tracer must never
		# stop the clock
		# ==================================================
		try:
			print(json.dumps(dataForTracer, indent=4, sort_keys=True)) # Debug
			responseJson = requests.post(CONTROLLER_KNFCLOCK_API_URL, json=dataForTracer, headers={'X-API-Key': KNFCLOCK_BRIDGE_API_KEY}).json()
			with open(CONTROLLER_CONFIG_FILENAME, 'w') as outfile:
				json.dump(responseJson, outfile)

			IsSystemTurnedOn = responseJson.get('IsSystemTurnedOn', IsSystemTurnedOn)
			DoNotLookAtSunriseTime = responseJson.get('DoNotLookAtSunriseTime', DoNotLookAtSunriseTime)
			Tracer_TurnOnOffset = responseJson.get('TurnOnOffset', Tracer_TurnOnOffset)
			Tracer_TurnOffOffset = responseJson.get('TurnOffOffset', Tracer_TurnOffOffset)
			#print(json.dumps(responseJson, indent=4, sort_keys=True)) # Debug
		except:
			pass


		time.sleep(KNFCLOCK_REFRESH_TIME)








if __name__ == '__main__':
	show_time_v1()
