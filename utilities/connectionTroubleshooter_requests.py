from pickle import TRUE
from stat import filemode
from tracemalloc import start
from urllib import request
import requests
import logging
import json
import http.client
import time

#Enter your printer's address here
duetAddress = "http://192.168.1.202"
timeoutSeconds = 2
sleepTime = 0.1
loops = 100

machineStatus = {
    "C": "Reading configuration file",
    "F": "Flashing new firmware",
    "H": "Halted (after e-stop)",
    "O": "Off (powered down, low input voltage)",
    "D": "Pausing print (decelerating)",
    "R": "Resuming print (after pause)",
    "S": "Print paused (stopped)",
    "M": "Simulating a print file",
    "P": "Printing",
    "T": "Changing tool",
    "B": "Busy (executing macro, moving)",
    "I": "Idle"
}

# http.client.HTTPConnection.debuglevel = 1
session = requests.Session()

# setup Logging to troubleshooting.log
# create a formatter and add it to the handlers
logging.basicConfig(
    filename="troubleshooting.log",  
    level=logging.DEBUG, 
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(name)s - %(funcName)s (%(lineno)d) - %(message)s'
    )

requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.INFO)
requests_log.propagate = TRUE

def getBuffer():
    startTime = time.time()
    response = requests.get( duetAddress + '/rr_gcode', timeout=timeoutSeconds ).json()
    duration = time.time() - startTime
    reply = requests.get( duetAddress + '/rr_reply', timeout=timeoutSeconds )
    buffer_size = int(response['buff'])
    logging.info( 'Query took: %.3f s.' % duration )
    logging.info( 'Buffer is currently %.0f bytes.' % buffer_size )
    return

def move():
    startTime = time.time()
    response = requests.get( duetAddress + '/rr_gcode?gcode=G91 G1 X0.5 Y0.5 F3000 G90', timeout=timeoutSeconds ).json()
    duration = time.time() - startTime
    reply = requests.get( duetAddress + '/rr_reply', timeout=timeoutSeconds )
    buffer_size = int(response['buff'])
    logging.info( 'Query took: %.3f s.' % duration )
    logging.info( 'Buffer is currently %.0f bytes.' % buffer_size )
    return

def homePrinter():
    homestartTime = time.time()
    response = requests.get( duetAddress + '/rr_gcode?gcode=G28 XY', timeout=timeoutSeconds ).json()
    duration = time.time() - homestartTime
    reply = requests.get( duetAddress + '/rr_reply', timeout=timeoutSeconds )
    while True:
        startTime = time.time()
        response = requests.get( duetAddress + '/rr_status?type=2', timeout = timeoutSeconds ).json()
        reply = requests.get( duetAddress + '/rr_reply', timeout=timeoutSeconds )
        duration = time.time() - homestartTime
        currentStatus = response['status']
        if currentStatus is not 'I':
            time.sleep(sleepTime)
            continue
        else:
            break
    logging.info('Homing took %.3f s.' % (time.time()-homestartTime))
    response = requests.get( duetAddress + '/rr_gcode?gcode=G1 X0 Y0 F3000', timeout=timeoutSeconds )
    return

def getCoords():
    startTime = time.time()
    while True:
        try:
            response = requests.get( duetAddress + '/rr_status?type=2', timeout = timeoutSeconds ).json()
            reply = requests.get( duetAddress + '/rr_gcode', timeout=timeoutSeconds ).json()
        except Exception as e1:
            print('Exception occurred!')
            print(str(e1))
            logger.error('Unhandled exception in getCoords: ' + str(e1))
            exit()
        duration = time.time() - startTime
        currentStatus = response['status']
        if currentStatus is not 'I':
            time.sleep(sleepTime)
            continue
        else:
            break
    logging.info( 'Response took %.3f s.' % duration )
    logging.info( reply['buff'])
    jc=response['coords']['xyz']
    an=response['axisNames']
    ret=json.loads('{}')
    for i in range(0,len(jc)):
        ret[ an[i] ] = jc[i]
    logging.info(ret)

if __name__=='__main__':
    programStartTime = time.time()
    # get initial buffer length
    print( 'Getting buffer initial size.. ')
    getBuffer()
    # create first connection
    print('Creating authenticated session.')
    logging.info('Creating authenticated session.')
    startTime = time.time()
    response = requests.get( duetAddress + '/rr_connect?password=reprap', timeout=timeoutSeconds )
    duration = time.time() - startTime
    getBuffer()
    logging.info( 'Query took: %.3f s.' % duration )
    logging.info( 'Response: ' )
    logging.info( response.json() )

    # Get firmware information
    startTime = time.time()
    response = requests.get( duetAddress + '/rr_status?type=2', timeout = timeoutSeconds ).json()
    reply = requests.get( duetAddress + '/rr_reply', timeout=timeoutSeconds )
    duration = time.time() - startTime

    print("Firmware name: " + response["firmwareName"])
    print("Firmware version: " + response["firmwareVersion"])
    logging.info( "Firmware name: " + response["firmwareName"] )
    logging.info( "Firmware version: " + response["firmwareVersion"] )

    print( 'Querying printer for coordinates %0i times...' % loops )
    logging.info( 'Querying printer for coordinates %0i times...' % loops )
    # home XY axes
    homePrinter()
    #execute moves
    execTime = time.time()
    avgTime = 0
    print('Without close headers..')
    # first off, no connection:close header
    session.headers.update({'Connection':'keep-alive'})
    for i in range(loops):
        print( 'Move %3i of %3i..\r' % ((i+1), loops ), end='')
        startTime = time.time()
        while True:
            response = requests.get( duetAddress + '/rr_status?type=2', timeout = timeoutSeconds )
            reply = requests.get( duetAddress + '/rr_reply', timeout=timeoutSeconds )
            logging.debug("HEADERS")
            logging.debug(response.headers)
            currentStatus = response.json()['status']
            if currentStatus is not 'I':
                time.sleep(sleepTime)
            else:
                break
        move()
        getCoords()
        duration = time.time() - startTime
        avgTime += duration
    print( 'Average response time is %.3f seconds.' % (avgTime/loops) )
    logging.info('Without close headers took %.3f seconds.' % (time.time()-execTime))
    print('Without close headers took %.3f seconds.' % (time.time()-execTime))

    # second, with connection:close header
    session.headers.update({'Connection':'close'})
    # home XY axes
    homePrinter()
    print('With close headers')
    avgTime = 0
    execTime = time.time()
    for i in range(loops):
        print( 'Move %3i of %3i..\r' % ((i+1), loops ), end='')
        startTime = time.time()
        while True:
            response = requests.get( duetAddress + '/rr_status?type=2', timeout = timeoutSeconds )
            reply = requests.get( duetAddress + '/rr_reply', timeout=timeoutSeconds )
            logging.debug("HEADERS")
            logging.debug(response.headers)
            currentStatus = response.json()['status']
            if currentStatus is not 'I':
                time.sleep(sleepTime)
            else:
                break
        move()
        getCoords()
        duration = time.time() - startTime
        avgTime += duration
    logging.info('With close headers took %.3f seconds.' % (time.time()-execTime))
    print( 'Average response time is %.3f seconds.' % (avgTime/loops) )
    print('With close headers took %.3f seconds.' % (time.time()-execTime))
    # get 
    #for _ in range(10):
    #    requests.get( (duetAddress + "/rr_status") )
    logging.info('Test complete in %0.3f seconds .' % (time.time() - programStartTime))