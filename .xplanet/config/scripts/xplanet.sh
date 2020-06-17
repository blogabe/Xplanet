#!/bin/zsh

SWITCH=$1
CMDRESPONSE=1

source /Users/$USER/.xplanet/config/xp.def

case "$SWITCH" in
    install)
        brew tap blogabe/xplanet
        brew install -s blogabe/xplanet/xplanet --without-giflib --with-cspice
        echo "Running Xplanet to bring up Mac security approvals"
        echo "Xplanet won't work without these approvals"
        echo "Accept fast... (10 seconds)"
        echo 'Press any key to continue or Control-C to exit...'; read -k1 -s
        `xplanet -num_times=1`
        sleep 8
        `xplanet -num_times=1`
        sleep 4
        echo -e "
Before running setup, make sure 'config' and its contents
are in your desired Xplanet home directory
  e.g., the dir '~/.xplanet/config/*' exists

The file 'config/xp.def' is sourced at the top of this script
make sure the location points to the file

'xp.def' also defines two variables that need to be checked:
XPLANET_BIN needs to point to the Xplanet executable
  run '/usr/bin/which xplanet'
XPLANET_HOME needs to reference the directory where 'config' is
  '~/.xplanet' in the above example
"
        ;;
    setup)
        echo "Setting up the Xplanet environment in ${XPLANET_HOME}"
        source $XPLANET_CONFIG/scripts/xp-setup.sh
        ;;
    start)
        $XPLANET_BIN \
            -searchdir=$XPLANET_HOME \
            -config=$XPLANET_CONFIG/xp.conf \
            -projection=$XPLANET_PROJECTION \
            -longitude=$XPLANET_LONGITUDE \
            -labelpos=+10-45 \
            -date_format="%D at %r" \
            -color=green2 \
            -fork
        ;;
    stop)
        # kill -9 $(ps aux | grep '[x]planet' | awk '{print $2}')
        killall xplanet
        ;;
    earth)
        # rm ${XPLANET_HOME}/logs/xplanet*
        MONTH=$(date +%m)
        LAND_FILE="${EARTH_MAP_PRE}.2004$MONTH.3x5400x2700.png"
        # unlink ${XPLANET_HOME}/images/earth.png
        ln -sfn ${XPLANET_CONFIG}/images/$LAND_FILE ${XPLANET_HOME}/images/earth.png
        ;;
    clouds)
        if [[ ! -z "$CLOUD_USER" ]]; then
            TEMP="-u ${CLOUD_USER}:${CLOUD_PWD} -z ${XPLANET_HOME}/images/${CLOUD_MAP} -R -L -o ${XPLANET_HOME}/images/${CLOUD_MAP} ${CLOUD_URL}/${CLOUD_MAP}"
            curl $TEMP
        else
            echo "$(date): ERROR! Updating clouds, but the username is not defined. Check $XPLANET_CONFIG/xp.def"
            exit 1;
        fi
        ;;
    *)
        clear
        echo -e "Options for this script:
./xplanet.sh
  'install' - installs Xplanet
  'setup'   - sets the Xplanet environment 
  'start'   - starts Xplanet in forked process
  'stop'    - stops all running instances of Xplanet
  'earth'   - updates the monthly Earth map and maintenance
  'clouds'  - updates the cloud map
"
        exit 1 ;;
esac

CMDRESPONSE=$?

if [ $CMDRESPONSE -eq 0 ]; then
    case "$SWITCH" in
        install)    echo "Xplanet is successfully installed (it should be the current background)" ;;
        setup)      echo "Xplanet environment setup is complete" ;;
        start)      echo "$(date): Xplanet Started" ;;
        stop)       echo "$(date): Xplanet Stopped" ;;
        earth)      echo "$(date): Earth Map Updated"
                    # echo "$(date): Pruned Logs"
            ;;
        clouds)     echo "$(date) Cloud Image Updated" ;;
    esac
else
    case "$SWITCH" in
        install)    echo "ERROR! Xplanet installation returned code '$CMDRESPONSE'" ;;
        setup)      echo "ERROR! Xplanet environment setup returned code '$CMDRESPONSE'" ;;
        start)      echo "$(date): ERROR! Xplanet couldn't start code '$CMDRESPONSE'" ;;
        stop)       echo "$(date): ERROR! Couldn't stop Xplanet processes, code '$CMDRESPONSE'" ;;
        earth)      echo "$(date): ERROR! Couldn't update Xplanet earth map, code '$CMDRESPONSE'"
                    # echo "$(date): ERROR! Couldn't prune Xplanet logs, code '$CMDRESPONSE'"
            ;;
        clouds)     echo "$(date): ERROR! Couldn't download Xplanet cloud image, code '$CMDRESPONSE'" ;;
    esac
fi
