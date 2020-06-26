echo "Setting directory structure and linking files"
cd ${XPLANET_HOME}
mkdir -p {arcs,images,logs,markers,satellites}
${XPLANET_CONFIG}/scripts/xplanet.sh earth
cd ${XPLANET_HOME}/images
ln -s ${XPLANET_CONFIG}/images/clouds-4096.jpg clouds-4096.jpg
ln -s ${XPLANET_CONFIG}/images/earth_lights_4800.tiff lights.tiff
ln -s ${XPLANET_CONFIG}/images/gebco_08_rev_elev_21600x10800.png bump.png
ln -s ${XPLANET_CONFIG}/images/specular.png specular.png
cd ${XPLANET_HOME}/markers
ln -s $(brew --prefix)/share/xplanet/markers/earth earth

echo ""
echo -e "
  The final part of the setup is to make Xplanet startup at login.
  
  If you do not want to do this, Control-C now.
  
  If you want to automate Xplanet's startup and updates, edit the
  working directory in the 3 files located at ${XPLANET_CONFIG}/scripts/plist
  by replacing '[username]' with '$USER'
  
"
echo 'Press any key to continue or Control-C to exit...'; read -k1 -s

echo "Copying plist files to automate startup and updates"
mkdir -p /Users/$USER/Library/LaunchAgents
cd /Users/$USER/Library/LaunchAgents
cp ${XPLANET_CONFIG}/scripts/plist/local.xplanet.* .

echo "Starting Xplanet..."
for plist_script (start earth-map clouds); do
    if [ -f local.xplanet.$plist_script.plist ]; then
        launchctl load -w local.xplanet.$plist_script.plist
        launchctl start local.xplanet.$plist_script
    else
        echo "WARNING local.xplanet.$plist_script.plist doesn't exist in ~/Library/LaunchAgents!"
        echo "Fix and start manually with:"
        echo "  launchctl load -w local.xplanet.$plist_script.plist"
        echo "  launchctl start local.xplanet.$plist_script"
    fi
done
echo "Expect another Apple security approval if this is running for the first time (wait 20 seconds)"
echo "Log out and back in after you approve"
cd ${XPLANET_HOME}
