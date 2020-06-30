echo "Setting home directory structure and linking cloud and marker files"
cd $XPLANET_HOME
mkdir -p {arcs,images,logs,markers,satellites}
$XPLANET_CONFIG/scripts/xplanet.sh earth
cd $XPLANET_HOME/images
ln -s $XPLANET_CONFIG/images/clouds/clouds-4096.jpg clouds-4096.jpg
ln -s $XPLANET_CONFIG/images/lights/earth_lights_4800.tiff lights.tiff
ln -s $XPLANET_CONFIG/images/bump/gebco_08_rev_elev_21600x10800.png bump.png
ln -s $XPLANET_CONFIG/images/specular/specular.png specular.png

echo "Configuring Xplanet"
echo -e "################################################################################
  Xplanet, on its own, is installed and configured. The rest of the setup,
  and only with your approval, will update the marker files and the cloud image
  in addition to automating the script execution to keep everything up to date.
  
  Step 1) Installs a necessary PERL module for Totalmarker to work and updates
          the marker files.

          Additionally, you can configure Totalmarker by editing
          $XPLANET_CONFIG/totalmarker.ini

  Step 2) Keeping the cloud image up to date requires a paid subscription to
          Xeric Designs: https://www.xericdesign.com/xplanet.php

          Subscribers need to update 'CloudUsername' and 'CloudPassword' in
          $XPLANET_CONFIG/totalmarker.ini

  Step 3) Automates Xplanet so that it loads on login and keeps the marker
          files up to date.

  You will be prompted to continue at each step."
echo "################################################################################"
echo 'Step 1) Press any key to continue or Control-C to exit...'; read -k1 -s

cd $XPLANET_HOME/markers
cp `(brew --prefix)`/share/xplanet/markers/earth earth
echo "Prepare marker files with Totalmarker"
cd $XPLANET_HOME
TMPL_LOC=$XPLANET_CONFIG/scripts/Totalmarker2.6.1.pl
ln -s $TMPL_LOC $TM
# Important we get this right now
if [ ! -L $TM ]; then
    echo "ERROR! Xplanet environment setup failed"
    echo "  Link to Totalmarker script doesn't point to anything... check and rerun"
    exit 1
fi
echo "Installing PERL module"
export PERL_MM_USE_DEFAULT=1
cpan Mozilla::CA > /dev/null
if [ ! -L $XPLANET_CONFIG/totalmarker.ini ]; then
    echo "Running Totalmarker for the first (and second time)"
    /usr/bin/perl $TM > /dev/null
    /usr/bin/perl $TM > /dev/null
    sed -i '' "s/clouds_2048.jpg/clouds-4096.jpg/" $XPLANET_CONFIG/totalmarker.ini
    sed -i '' "s/Username/CloudUsername/" $XPLANET_CONFIG/totalmarker.ini
    sed -i '' "s/Password/CloudPassword/" $XPLANET_CONFIG/totalmarker.ini
fi
echo "Updating markers"
/usr/bin/perl $TM -Volcano
/usr/bin/perl $TM -Storm
/usr/bin/perl $TM -Quake
PLISTS=('start' 'earth-map' 'quake' 'storm' 'volcano')
open -e $XPLANET_CONFIG/totalmarker.ini
echo -e "################################################################################
********************************************************************************
  Now is a good time to review and edit Totalmarker's initialization file at
  $XPLANET_CONFIG/totalmarker.ini

  You may want to change QuakeMinimumSize

  Subscribers to Xeric Designs cloud service need to update 'CloudUsername' and
  'CloudPassword' credentials now before moving on
********************************************************************************"
read -k1 "YESNO?Step 2) Are you subscribing to Xeric Designs for the cloud updates? "
if [[ "$YESNO" =~ ^[Yy]$ ]]; then
    echo "\nUpdating cloud image"
    unlink $XPLANET_HOME/images/clouds-4096.jpg
    /usr/bin/perl $TM -Clouds
    PLISTS+=('clouds')
fi

echo "\nAutomating script execution so that Xplanet loads and updates when you log in"
echo "################################################################################"
read -k1 "YESNO?Step 3) Do you want to automate Xplanet startup w/ Totalmarker updates? "
if [[ "$YESNO" =~ ^[Yy]$ ]]; then
    echo "\nCopying plist files to automate startup and updates"
    sed -i '' "s/<USERNAME>/$USER/" $XPLANET_CONFIG/scripts/plist/*.plist
    mkdir -p /Users/$USER/Library/LaunchAgents
    cd /Users/$USER/Library/LaunchAgents

    echo "Starting Xplanet..."
    for plist_script in $PLISTS; do
        cp $XPLANET_CONFIG/scripts/plist/local.xplanet.$plist_script.plist .
        launchctl load -w local.xplanet.$plist_script.plist
        launchctl start local.xplanet.$plist_script
    done
    echo "********************************************************************************"
    echo "  You may receive another Apple security approval\n  if this is running for the first time (wait 10 seconds)"
    echo "********************************************************************************"
fi
cd $XPLANET_HOME
