####################################
# ORIGINALLY WRITTEN BY MICHAEL DEAR
####################################

#! /usr/bin/perl

#perl2exe_include "Bzip2.pm";
#perl2exe_include "FileSpec.pm";

#perl2exe_include "C:/Perl2exe/v11/pm/FileSpec.pm";
#perl2exe_include "C:/Perl2exe/v11/pm/Bzip2.pm";
#perl2exe_include "C:/Perl2exe/v11/pm/FindBin.pm";

BEGIN {
    # CollapsedSubs: get_webpage  get_program_version  changelog_print  file_header  get_hurricanedata  WriteoutVolcano  get_volcanodata  update_file  get_eclipsedata  readineclipseindex  readineclipsetrack  datacurrent  writeouteclipsemarker  writeouteclipsearcboarder  writeouteclipsearccenter  writeouteclipsefilesnone  writeouteclipselabel  refinedata  get_settings  easteregg
    $0 = $^X unless ($^X =~ m%(^|[/\\])(perl)|(perl.exe)$%i );
}
use FindBin qw($Script $Bin);
use LWP::UserAgent;
use LWP::Simple;
use Time::Local;
use HTTP::Response;
use HTTP::Cookies; 
use HTTP::Request; 
use File::Copy;
use File::Spec;
use Mozilla::CA;

our $VERSION="2.6.1";
$Client = "Client Edition";
$Script = "TotalMarker";

################################################################################################
#
#
#        Configuaration section.  Please Check these varibles and adjust
#
#
################################################################################################
#
# Orgininal Location of the downloads
#
my $quake_location = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.csv";
my $storm_base_location = "https://www.nrlmry.navy.mil/tcdat/sectors/ftp_sector_file";
my $storm_past_location = "https://www.nrlmry.navy.mil/archdat/test/kml/TC/";
my $storm_future_location = "https://www.nrlmry.navy.mil/atcf_web/docs/current_storms/";
my $iss_location = "https://www.celestrak.com/NORAD/elements/stations.txt";
my $other_locations1 = "https://www.celestrak.com/NORAD/elements/science.txt";
my $hst_location = "https://www.celestrak.com/NORAD/elements/tdrss.txt";
my $sts_location = "https://www.celestrak.com/NORAD/elements/sts.txt";
my $sts_dates = "https://www.seds.org/~spider/shuttle/shu-sche.html";
my $backup_sat_location= "https://www.idb.com.au/joomla/index.php";
#my $volcano_location = "https://www.volcano.si.edu/bgvn.cfm";
#my $volcano_location = "https://www.volcano.si.edu/news/WeeklyVolcanoCAP.xml";
my $volcano_location = "https://volcano.si.edu/news/WeeklyVolcanoCAP.xml";
my $eclipse_location = "https://sunearth.gsfc.nasa.gov/eclipse/SEpath/";
my $refined_eclipse_data = "https://www.wizabit.eclipse.co.uk/xplanet/files/local/update.data";
#my $cloud_image_base = "https://xplanetclouds.com/free/coral/";
my $cloud_image_base = "https://secure.xericdesign.com/xplanet/clouds/4096";

my $volcano_location_RSS_24H = "https://earthquake.usgs.gov/eqcenter/recenteqsww/catalogs/caprss1days2.5.xml";

my $quake_location_CSV_24H_SIG = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_day.csv";
my $quake_location_CSV_24H_45 = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.csv";
my $quake_location_CSV_24H_25 = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.csv";
my $quake_location_CSV_24H_10 = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/1.0_day.csv";
my $quake_location_CSV_24H_ALL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.csv";

my $quake_location_CSV_7D_SIG = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.csv";
my $quake_location_CSV_7D_45 = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.csv";
my $quake_location_CSV_7D_25 = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_week.csv";
my $quake_location_CSV_7D_10 = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/1.0_week.csv";
my $quake_location_CSV_7D_ALL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.csv";

my $quake_location_CSV_30D_SIG = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_month.csv";
my $quake_location_CSV_30D_45 = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_month.csv";
my $quake_location_CSV_30D_25 = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_month.csv";
my $quake_location_CSV_30D_10 = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/1.0_month.csv";
my $quake_location_CSV_30D_ALL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_month.csv";

$ua = LWP::UserAgent->new();
$ua->env_proxy();
$ua->agent("Mozilla/4.0 (compatible; MSIE 5.5; Windows NT 9.1)");

# Please note if you are using Windows and Active Perl you must \\ your directories not just use \
# where xplanet is installed
#
# Directory Layout
#
# my $xplanet_dir = $ENV{'XPLANET_DIR'} || "/usr/X11R6/share/xplanet";
my $xplanet_dir = $ENV{'XPLANET_DIR'} || $Bin;

# where the xplanet marker files are
my $xplanet_markers_dir = $ENV{'XPLANET_MARKERS_DIR'} || "$xplanet_dir/markers";

# where the xplanet greatarc files are
my $xplanet_arcs_dir = $ENV{'XPLANET_ARC_DIR'} || "$xplanet_dir/arcs";

# where the satellites info files are
my $xplanet_satellites_dir = $ENV{'XPLANET_SATELLITES_DIR'} || "$xplanet_dir/satellites";

# where the image files are
 $xplanet_images_dir = $ENV{'XPLANET_IMAGE_DIR'} || "$xplanet_dir/images";

# where the config files are
my $xplanet_config_dir = $env{'XPLANET_CONFIG_DIR'} || "$xplanet_dir/config";

#
# File Locations
#
# where the quake marker will be written to
my $quake_marker_file = " $xplanet_markers_dir/quake";

# where the volcano marker will be written to
my $volcano_marker_file = " $xplanet_markers_dir/volcano";

# where the hurricane marker will be written to
my $hurricane_marker_file = " $xplanet_markers_dir/storm";

# where the hurricane tracking will be written to
my $hurricane_arc_file = " $xplanet_arcs_dir/storm";

# where the iss file will be written to
$iss_file = "$xplanet_satellites_dir/tm";

#where the iss.tle will be written to
$isstle_file = "$xplanet_satellites_dir/tm.tle";

#where the iss.tle will be written to
my $label_file = "$xplanet_markers_dir/updatelabel";

#where the eclipse marker file will be written to
my $eclipse_marker_file = "$xplanet_markers_dir/eclipse";

#where the eclipse arc file will be written to
my $eclipse_arc_file = "$xplanet_arcs_dir/eclipse";

#where the eclipse data file will be written to
my $eclipse_data_file = "$xplanet_config_dir/totalmarker.dat";

#where the settings are stored
my $settings_ini_file = "$xplanet_config_dir/totalmarker.ini";

#where the old settings were stored
my $settings_old_ini_file = "$xplanet_dir/totalmarker.ini";

#where the old dat files was stored
my $eclipse_old_data_file = "$xplanet_dir/totalmarker.dat";

#where cloud batch file is
my $cloudbatch = "$xplanet_dir/updateclouds.bat";

#Where WinXplanetbg stores its settings
my $winXPlanetBG = "$xplanet_dir/winXPlanetBG.ini";

#Where the backup is stored
my $winxplanetbgbackup = "xplanet_config_dir/winXPlanetBG.ini";

#
# Test that locations exist and can be written to.
#
-d $xplanet_dir         || die("Could not find xplanet installation directory $xplanet_dir\n");
-r $xplanet_dir         || die("Could not read from xplanet installation directory $xplanet_dir\n");
-w $xplanet_dir         || die("Could not write to xplanet installation directory $xplanet_dir\n");
-e $eclipse_data_file   || &install(eclipsfile);
-e $settings_ini_file   || &install(configfile);

-d $xplanet_markers_dir || die("Could not find xplanet markers directory $xplanet_markers_dir\n");
-r $xplanet_markers_dir || die("Could not read fromxplanet markers directory $xplanet_markers_dir\n");
-w $xplanet_markers_dir || die("Could not write to xplanet markers directory $xplanet_markers_dir\n");

-d $xplanet_arcs_dir || die("Could not find xplanet arcs directory $xplanet_arc_dir\n");
-r $xplanet_arcs_dir || die("Could not read from xplanet arcs directory $xplanet_arc_dir\n");
-w $xplanet_arcs_dir || die("Could not write to xplanet arcs directory $xplanet_arc_dir\n");

-d $xplanet_satellites_dir || die("Could not find xplanet satellites directory $xplanet_satellites_dir\n");
-r $xplanet_satellites_dir || die("Could not read from xplanet satellites directory $xplanet_satellites_dir\n");
-w $xplanet_satellites_dir || die("Could not write to xplanet satellites directory $xplanet_satellites_dir\n");

-d $xplanet_images_dir || die("Could not find xplanet images directory $xplanet_images_dir\n");
-r $xplanet_images_dir || die("Could not read xplanet from images directory $xplanet_images_dir\n");
-w $xplanet_images_dir || die("Could not write xplanet to images directory $xplanet_images_dir\n");

#
# Allows simple update to Totalmarker should regex & location change.
#
$readfile="totalmarker.upd";
if ( (-e $readfile) && (-r $readfile) ) {
    &get_xml_update;
}



sub get_webpage($) {
    my ($URL)=@_;
    my $req = HTTP::Request->new(GET => $URL);
    my $res = $ua->request($req);
    
    return $res->content || return FAILED;
}

sub command_line {
    while (@ARGV) {
        $result = shift @ARGV;
        if (substr($result,0,1) eq "-") {
            if ($result eq "-earthquake")           {$quake_on_off = 1;}
            elsif ($result eq "-Label")             {$update_label= 1;}
            elsif ($result eq "-label")             {$update_label= 1;}
            elsif ($result eq "-Earthquake")        {$quake_on_off = 1;}
            elsif ($result eq "-Quake")             {$quake_on_off = 1;}
            elsif ($result eq "-Volcano")           {$volcano_on_off = 1;}
            elsif ($result eq "-NORAD")             {$norad_on_off = 1;}
            elsif ($result eq "-Norad")             {$norad_on_off = 1;}
            elsif ($result eq "-Clouds")            {$clouds_on_off = 2;}
            elsif ($result eq "-Cloud")             {$clouds_on_off = 2;}
            elsif ($result eq "-Hurricane")         {$hurricane_on_off = 1;}
            elsif ($result eq "-Storm")             {$hurricane_on_off = 1;}
            elsif ($result eq "-quake")             {$quake_on_off = 1;}
            elsif ($result eq "-volcano")           {$volcano_on_off = 1;}
            elsif ($result eq "-norad")             {$norad_on_off = 1;}
            elsif ($result eq "-clouds")            {$clouds_on_off = 2;}
            elsif ($result eq "-cloud")             {$clouds_on_off = 2;}
            elsif ($result eq "-clouddone")         {$clouds_on_off = 1;}
            elsif ($result eq "-cloudsdone")        {$clouds_on_off = 1;}
            elsif ($result eq "-Clouddone")         {$clouds_on_off = 1;}
            elsif ($result eq "-Cloudsdone")        {$clouds_on_off = 1;}
            elsif ($result eq "-hurricane")         {$hurricane_on_off = 1;}
            elsif ($result eq "-storm")             {$hurricane_on_off = 1;}
            elsif ($result eq "-version") {
                my $xplanetversion = &get_program_version;
                print "$Script $Client $VERSION\nXplanet Version $xplanetversion\nMichael Dear    10th Feb 2004\nhttp://www.wizabit.eclipse.co.uk/xplanet\n";
                exit 1;
                die;
            }
            elsif ($result eq "-Version") {
                my $xplanetversion = &get_program_version;
                print "$Script $Client $VERSION\nXplanet Version $xplanetversion\nBy Michael Dear    10th Feb 2004\nhttp://www.wizabit.eclipse.co.uk/xplanet\n";
                exit 1;
                die;
            }
            elsif ($result eq "-update") {&update_ini_file; exit 1;}
            elsif ($result eq "-Update") {&update_ini_file; exit 1;}
            elsif ($result eq "-install") {
                $result = shift @ARGV;
                if ($result =~ /storm/)             {&install(storm);}
                elsif ($result =~ /hurricane/)      {&install(storm);}
                elsif ($result =~ /quake/)          {&install(quake);}
                elsif ($result =~ /norad/)          {&install(norad);}
                elsif ($result =~ /cloud/)          {&install(cloud);}
                elsif ($result =~ /volcano/)        {&install(volcano);}
                elsif ($result =~ /Storm/)          {&install(storm);}
                elsif ($result =~ /Hurricane/)      {&install(storm);}
                elsif ($result =~ /Quake/)          {&install(quake);}
                elsif ($result =~ /Norad/)          {&install(norad);}
                elsif ($result =~ /NORAD/)          {&install(norad);}
                elsif ($result =~ /Cloud/)          {&install(cloud);}
                elsif ($result =~ /eclipse/)        {&install(eclipse);}
                elsif ($result =~ /Eclipse/)        {&install(eclipse);}
                elsif ($result =~ /UpdateLabel/)    {&install(updatelabel);}
                elsif ($result =~ /updatelabel/)    {&install(updatelabel);}
                elsif ($result =~ /Updatelabel/)    {&install(updatelabel);}
                elsif ($result =~ /Volcano/)        {&install(volcano);}
                elsif ($result =~ /TotalMarker/)    {&install(totalmarker);}
                elsif ($result =~ /totalmarker/)    {&install(totalmarker);}
                elsif ($result =~ /Totalmarker/)    {&install(totalmarker);}
                elsif ($result =~ /ChangeLog/)      {&changelog_print(all);}
                elsif ($result =~ /Changelog/)      {&changelog_print(all);}
                elsif ($result =~ /changelog/)      {&changelog_print(all);}
                elsif ($result =~ /changeLog/)      {&changelog_print(all);}
                else {
                    &get_it_right_install();
                }
            }
            elsif ($result eq "-Install") { 
                $result = shift @ARGV;
                if ($result =~ /storm/)             {&install(storm);}
                elsif ($result =~ /hurricane/)      {&install(storm);}
                elsif ($result =~ /quake/)          {&install(quake);}
                elsif ($result =~ /norad/)          {&install(norad);}
                elsif ($result =~ /cloud/)          {&install(cloud);}
                elsif ($result =~ /volcano/)        {&install(volcano);}
                elsif ($result =~ /Storm/)          {&install(storm);}
                elsif ($result =~ /Hurricane/)      {&install(storm);}
                elsif ($result =~ /Quake/)          {&install(quake);}
                elsif ($result =~ /Norad/)          {&install(norad);}
                elsif ($result =~ /NORAD/)          {&install(norad);}
                elsif ($result =~ /Cloud/)          {&install(cloud);}
                elsif ($result =~ /eclipse/)        {&install(eclipse);}
                elsif ($result =~ /Eclipse/)        {&install(eclipse);}
                elsif ($result =~ /UpdateLabel/)    {&install(updatelabel);}
                elsif ($result =~ /updatelabel/)    {&install(updatelabel);}
                elsif ($result =~ /Updatelabel/)    {&install(updatelabel);}
                elsif ($result =~ /Volcano/)        {&install(volcano);}
                elsif ($result =~ /TotalMarker/)    {&install(totalmarker);}
                elsif ($result =~ /totalmarker/)    {&install(totalmarker);}
                elsif ($result =~ /Totalmarker/)    {&install(totalmarker);}
                elsif ($result =~ /ChangeLog/)      {&changelog_print(all);}
                elsif ($result =~ /Changelog/)      {&changelog_print(all);}
                elsif ($result =~ /changelog/)      {&changelog_print(all);}
                elsif ($result =~ /changeLog/)      {&changelog_print(all);}
                else {
                    &get_it_right_install();
                }
            }
            else {
                get_it_right_lamer();
            }
        }
        else {
            get_it_right_lamer();
        }
    }
}

sub get_program_version () {
    my $programversion = `xplanet --version`;
    foreach (split("\n",$programversion)) {
        if ($_ =~ /Xplanet/) {
            s/ //g;
            s/Xplanet//g;
            return $_;
        }
    }
}

sub changelog_print () {
    my $oldversion = @_;
    #header
    print "Present Version is $VERSION. Installed settings file version is $oldversion\n";
    print "This is the Changelog from versions $oldversion to $VERSION\n";
    #changelog
    my $flag = 99999;
    if ($oldversion =~ /1/)         {$flag = 1;}
    if ($oldversion =~ /1.03.1/)    {$flag = 1;}
    if ($oldversion =~ /1.03.2/)    {$flag = 2;}
    if ($oldversion =~ /1.03.3/)    {$flag = 3;}
    if ($oldversion =~ /1.03.4/)    {$flag = 4;}
    if ($oldversion =~ /2.5.0/)     {$flag = 5;}
    if ($oldversion =~ /2.5.1/)     {$flag = 6;}
    if ($oldversion =~ /2.5.2/)     {$flag = 7;}
    if ($oldversion =~ /2.5.6/)     {$flag = 8;}
    if ($oldversion =~ /3.0.0/)     {$flag = 9;}
    if ($oldversion =~ /all/)       {$flag = 6;}
    if ($flag == 1) {
        print"\n *1.03.2\n";
        print"  Added a Satellite file name option. i.e. NoradFileName=tm (*)\n";
        print"  Added a Eclipse notification in hours. i.e. EclipseNotifyTimeHours=48 (*)\n";
        print"  Fixed the after event notification for Eclipses\n";
        print"  Added a version Option. -version\n";
        print"  Added an install option to update files and setup it self up\n";
        print"  Made it so that it knows about XplanetNG\n";
        print"  Moved the settings and data files to /config for use with XplanetNG\n";
        print"  Fixed a Earthquake bug that would not show some Earthquakes\n";
        print"  If the data fails to give a magnitude 0.0 will show and a circle of 4 is drawn\n";
        if ($VERSION =~ /1.03.2/) {$flag = 99999;}
    }
    if ($flag <= 2) {
        print"\n *1.03.2\n";
        print"  Symbolsize has changed for version 0.95 and above Earthquakes circles work as\n before Volcano need changing to 2,4,6 in ini file\nAdded an option to download the cloud image.\n";
        if ($VERSION =~ /1.03.3/) {$flag = 99999;}
    }
    if ($flag <= 3) {
        print"\n *2.04.1\n";
        print"  Fixed Labels\nAdded a modem option for labelupdate\nChanged version to internal version numbering.\nDefaults to downloading TLE of Science Orbits";
        if ($VERSION =~ /1.03.4/) {$flag = 99999;}
    }
    if ($flag <= 4) {
        print"\n *2.04.2\n";
        print"  Fixed miss labeled QuakeMinSize to QuakeMinimumSize\nAdded the Option for Soyuz\nAdded a flag of Xplanet version.\n ";
        if ($VERSION =~ /1.03.5/) {$flag = 99999;}
    }
    if ($flag <= 5) {
        print"\n *2.5.0\n";
        print"  Versions changed to match internal CVS\nInternal chages made and setup for Xplanet 1.0 or better";
        if ($VERSION =~ /1.03.6/) {$flag = 99999;}
    }
    if ($flag <= 6) {
        print"\n *2.5.1\n";
        print"  USGS changed pages, a rewrite of the quake data to get it working again.\nFixed minor bugs in quake and storm details.";
        if ($VERSION =~ /1.03.7/) {$flag = 99999;}
    }
    if ($flag <= 7) {
        print"\n *2.5.2\n";
        print"  Fixed Storms not working over to new website.\n";
        if ($VERSION =~ /1.03.7/) {$flag = 99999;}
    }
    if ($flag <= 8) {
        print"\n *2.5.6\n";
        print"  Fixed Storms and Earthquakes not working over to new website.\n";
        if ($VERSION =~ /1.03.7/) {$flag = 99999;}
        print"\n *2.5.7\n";
        print"  Fixed Storms Track added a difference check as source data was wrong, sorted by ignoring data that is +/- 5 f last reported postiion for past data.\n";
    }
    if ($flag <= 9) {
        print"\n 3.0.0\n";
        print"  Using RSS where possable\n";
        print"  Moved to new platform\n";
        if ($VERSION =~ /1.03.7/) {$flag = 99999;}
    }
    #ending
    print"\nThe items with a (*) by them are accessible if you allow totalmarker to update its files. To add the extra settings to TotalMarker please run:\n\"TotalMarker -install totalmarker patch\" without the quotes.\n";
    print"\nTo see the entire log please type \n\"TotalMarker -install totalmarker |more\" with out the quotes.\n";
    print"\nVersion: $VERSION         Home: http://www.wizabit.eclipse.co.uk/xplanet";
    exit 1;
    die;
}

sub get_it_right_install {
    print <<EOM;
$Script: download and create marker files to be used with xplanet.
THIS IS IN BETA BACKUP YOUR WINXPLANETBG.INI FILE BEFORE USING.
 The install section will accept the following options
* $Script -install Quake   This will install Earthquakes into WinXplanetBG.
* $Script -install Storm   This will install Storms into WinXplanetBG.
* $Script -install Norad   This will install Satellitess into WinXplanetBG.
* $Script -install Volcano This will install Volcanos into WinXplanetBG.
* $Script -install Clouds  This will install Clouds into WinXplanetBG.
* $Script -install Eclipse This will install Eclipses into WinXplanetBG.
* $Script -install UpdateLabel This will install updatelabel into WinXplanetBG.
* $Script -install TotalMarker See Below.

Please Note:  Updating only works if you have WinXplanetBG. The Rest of you
can work it out for yourselves :P

* Install $Script.
As more options are added to each version, this will add the extra options
to the config file, so you can change them if you wish, they will default
to no changes from the past operations, if you do nothing, or don't
run this option.

Version: $VERSION         Home: http://www.wizabit.eclipse.co.uk/xplanet
EOM
    exit 1;
    die;
}

sub get_it_right_lamer {
    print <<EOM;
$Script: download and create marker files to be used with xplanet.

This script is driven by the command line, the options are as follows
* $Script -Quake      This will write the Earthquake marker file.
* $Script -Storm      This will write the Storm marker and arc files.
* $Script -Norad      This will write the ISS and ISS.TLE files.
* $Script -Volcano    This will write the Volcano marker file.
* $Script -Clouds     This will download the latest cloud image.
Eclipses and Updatelabel are controlled from the ini file.
If you are using an old totalmarker then run totalmarker -update
Options are set from the ini file.  This is created the first time the
file is run.  Please note it does require an Internet connection for
the first run, as it builds a database for the eclipses.

Then add the following to your xplanets config file under earths section
* -markerfile quake                                For Earthquakes
* -markerfile volcano                              For Volcanos
* -satfile tm (unless changed in the settings file)For Satellites
* -markerfile storm -greatarcfile storm            For Storms
* -markerfile updatelabel                          For UpdateLabel
* -markerfile eclipse -greatarcfile eclipse        For Eclipse

Version: $VERSION         Home: http://www.wizabit.eclipse.co.uk/xplanet
EOM
    exit 1;
    die;
}

sub cloud_update() {
    my $flag = 1;
    my $MaxDownloadFrequencyHours = 2;
    my $MaxRetries = 3;
    my $cloud_image_file = "$xplanet_images_dir/$cloudsettings->{'CloudLocalImageName'}";
    #print "$cloud_image_file\n";
    
    # Get file details
    if (-f $cloud_image_file) {
        my @Stats = stat($cloud_image_file);
		my $FileAge = (time() - $Stats[9]);
		my $FileSize = $Stats[7];
        
		# Check if file is already up to date
		if ($FileAge < 60 * 60 * $MaxDownloadFrequencyHours && $FileSize > 400000) {
		    print "  Cloud image is up to date... no need to download\n";
            $flag = 3;
		}
    }
    
    if ($flag != 3) {
        # TODO: fix this block as it's never executed
        # if ($cloudsettings->{'CloudBias'} =~ /\w/) {
        #     my $BiasFile = "$cloud_image_base/$cloudsettings->{'CloudRemoteImageName'}";
        #     my $Response = getstore($BiasFile, $cloud_image_file);
        #     if ( IndicatesSuccess($Response)) {
        #         $flag = 2;
        #     }
        # }
        
        # TODO - move away from curl to something perl specific
        # TODO - make this subroutine more robust with error checking as originally intended
        # TODO - and consistent with the rest of the script, specifically the cloudsettings definition and variable names
        my $download_string = "curl -s -u $cloudsettings->{'Username'}:$cloudsettings->{'Password'} -z $cloud_image_file -R -L -o $cloud_image_file $cloud_image_base/$cloudsettings->{'CloudRemoteImageName'}";
        my $Response = `$download_string`;
        if ( IndicatesSuccess($Response)) {
            # if this shows up in the logs then find out how/why
            print "  Updated cloud image (IF YOU SEE THIS IN THE LOGS THEN THERE IS A PROBLEM)\n";
            $flag = 2;
        }
        # the above conditional is never met so forcing this statement implying an attempt was made, but didn't receive http code 2xx implying success downloading
        print "  Updated cloud image\n";
    }
    
    return $flag;
}

# Return codes of 200 to 299 are "success" in HTTP-speak
sub IndicatesSuccess () {
    my $Response = shift();
    if ($Response =~ /2\d\d/)   {return(1);}
    else                        {return(0);}
}

# Returns the name of an internet resource which can provide the clouds image
sub GetRandomMirror() {
    # Populate a list of mirrors
    my @Mirrors;
    if ($cloudsettings->{'CloudMirrorA'} =~ /\w/) {push @Mirrors, "$cloudsettings->{'CloudMirrorA'}";}
    if ($cloudsettings->{'CloudMirrorB'} =~ /\w/) {push @Mirrors, "$cloudsettings->{'CloudMirrorB'}";}
    if ($cloudsettings->{'CloudMirrorC'} =~ /\w/) {push @Mirrors, "$cloudsettings->{'CloudMirrorC'}";}
    if ($cloudsettings->{'CloudMirrorD'} =~ /\w/) {push @Mirrors, "$cloudsettings->{'CloudMirrorD'}";}
    if ($cloudsettings->{'CloudMirrorE'} =~ /\w/) {push @Mirrors, "$cloudsettings->{'CloudMirrorE'}";}
    if ($cloudsettings->{'CloudMirrorF'} =~ /\w/) {push @Mirrors, "$cloudsettings->{'CloudMirrorF'}";}
    if ($cloudsettings->{'CloudMirrorG'} =~ /\w/) {push @Mirrors, "$cloudsettings->{'CloudMirrorG'}";}
    if ($cloudsettings->{'CloudMirrorH'} =~ /\w/) {push @Mirrors, "$cloudsettings->{'CloudMirrorH'}";}
    if ($cloudsettings->{'CloudMirrorI'} =~ /\w/) {push @Mirrors, "$cloudsettings->{'CloudMirrorI'}";}
    if ($cloudsettings->{'CloudMirrorJ'} =~ /\w/) {push @Mirrors, "$cloudsettings->{'CloudMirrorJ'}";}
    if ($cloudsettings->{'CloudMirrorK'} =~ /\w/) {push @Mirrors, "$cloudsettings->{'CloudMirrorK'}";}
    if ($cloudsettings->{'CloudMirrorL'} =~ /\w/) {push @Mirrors, "$cloudsettings->{'CloudMirrorL'}";}
    if ($cloudsettings->{'CloudMirrorM'} =~ /\w/) {push @Mirrors, "$cloudsettings->{'CloudMirrorM'}";}
    if ($cloudsettings->{'CloudMirrorN'} =~ /\w/) {push @Mirrors, "$cloudsettings->{'CloudMirrorN'}";}
    
    # Return one at random
    return $Mirrors[rand scalar(@Mirrors)];
}

# $browser->credentials(
#     #http://www.xplanetclouds.com/clouds/4096/clouds_clouds_4096.jpg
#     #http://www.xplanetclouds.com/clouds/4096/clouds_clouds_2048.jpg
#     '$site:80',
#     'www.xplanetclouds.com',
#     'maxsendq' => 'wh0tugot'
# );

# sub get_store () {
#     my ($file)=@_;
#     my $gif_URL="http://www.wizabit.eclipse.co.uk/xplanet/files/local/images/$file";
#     my ($name,$ext) = split '\.',$file,2;
#     my $outfile= "$xplanet_images_dir/$file";
#
#     $content = get_webpage($gif_URL );
#     if ($content eq undef) {}
#     else {
#         open(IMAGE,">$outfile")
#         binmode IMAGE;
#         print IMAGE $content;
#         close (IMAGE);
#     }
# }

sub file_header($) {
    my ($openfile) = @_;
    print MF "# This $openfile marker file created by $Script - $Client version $VERSION\n";
    print MF "# For more information read the top of the $Script file or go to\n";
    print MF "# http://www.wizabit.eclipse.co.uk/xplanet\n";
    $tsn = localtime(time);
    print MF "# Last Updated: $tsn\n#\n";
}

sub drawcircle($) {
    my ($mag)=@_;
    my $pixel;
    
    if ($quakesettings->{'QuakePixelMax'} =~ /\d/ && $quakesettings->{'QuakePixelMin'} !~ /\d/) {
        $pixel = max_model($mag);
    } elsif ($quakesettings->{'QuakePixelMax'} !~ /\d/ && $quakesettings->{'QuakePixelMin'} =~ /\d/) {
        $pixel = standard_model($mag);
        $pixel = $pixel + $quakesettings->{'QuakePixelMin'};
    } elsif ($quakesettings->{'QuakePixelMax'} =~ /\d/ && $quakesettings->{'QuakePixelMin'} =~ /\d/) {
        $pixel = max_min_model($mag);
    } else {
        $pixel = standard_model($mag);
    }
    
    if ($settings->{'XplanetVersion'} =~ /\w/) {
        if  ($settings->{'XplanetVersion'} =~ /es/) {
            return $pixel;
        }
		else {
            my $xplanetversion = &get_program_version();
            
            if ($xplanetversion =~ /(\d.\d\d)(\w)/) {
                my ($pversion,$prevision) = ($1,$2);
                $pversion *= 1;
            }
            
            if ($pversion < 0.99) {
                $pixel = $pixel*2;
            }
            
			return $pixel; 
		}
	}
}

sub max_model() {
    my ($mag)=@_;
    my $pixel = $quakesettings->{'QuakePixelMax'} / 10;
    
    $pixel = $pixel * $mag;
    
    return $pixel;
}

sub max_min_model() {
    my ($mag)=@_;
    my $max_pixel = $quakesettings->{'QuakePixelMax'};
    my $min_pixel = $quakesettings->{'QuakePixelMin'};
    my $pixel_diff = $max_pixel - $min_pixel;
    my $pixel = $pixel_diff / 10;
    
    $pixel = $pixel * $mag;
    $pixel = $pixel_diff + $min_pixel;
    
    return $pixel;
}

sub standard_model() {
    my ($mag)=@_;
    my $factor = $quakesettings->{'QuakePixelFactor'};
    my $pixel = $mag / 0.1;
    
    $pixel = $pixel * 2;
    $pixel = $pixel + 4;
    $pixel = $pixel * $factor;
    
    return $pixel;
}

sub get_file() {
    my ($file)=@_;
    my $gif_URL="http://www.wizabit.eclipse.co.uk/xplanet/files/local/images/$file";
    my ($name,$ext) = split '\.',$file,2;
    my $outfile= "$xplanet_images_dir/$file";
    
    $content = get_webpage($gif_URL );
    
    if ($content eq undef) {}
    else {
        open(IMAGE,">$outfile");
        binmode IMAGE;
        print IMAGE $content;
        close (IMAGE);
    }
}

sub colourisetext($) {
    my ($mag)=@_;
    
    if ($quakesettings->{'QuakeDetailColor'} !~ /Multi/) {
        return $quakesettings->{'QuakeDetailColor'};
    }
    else {
        return "$quakesettings->{'QuakeDetailColorMin'}" if $mag < 4.5;
        return "$quakesettings->{'QuakeDetailColorInt'}" if $mag < 6.5;
        return "$quakesettings->{'QuakeDetailColorMax'}" if $mag < 8.5;
        return 'White';
    }
}

sub colourisemag($) {
    my ($mag)=@_;
    
    if ($quakesettings->{'QuakeCircleColor'} !~ /Multi/) {
        return $quakesettings->{'QuakeCircleColor'};
    }
    else {
        return 'SeaGreen'               if $mag < 2.5;
        return 'PaleGreen'              if $mag < 3.0;
        return 'Green'                  if $mag < 3.5;
        return 'ForestGreen'            if $mag < 4.0;
        return 'Khaki'                  if $mag < 4.5; # Structal Damage
        return 'LightGoldenrodYellow'   if $mag < 5.0;
        return 'Yellow'                 if $mag < 5.5;
        return 'DarkGoldenrod'          if $mag < 6.0;
        return 'Salmon'                 if $mag < 6.5; # Major Damage
        return 'Orange'                 if $mag < 7.0;
        return 'Tomato'                 if $mag < 7.5;
        return 'OrangeRed'              if $mag < 8.0;
        return 'Red'                    if $mag < 8.5; # End of Scale
        return 'White'                  if $mag < 10; # We are in the sh1t now :P
        return 'Aquamarine';
    }
}

sub make_directory() {
    my ($target)=@_;
    
    -f $target && return 0;
    -d $target && return 1;
    
    my ($volume,$directories,$file) = File::Spec->splitpath( $target );
    $directories = File::Spec->catfile($directories,$file);
    $file="";
    
    my @dirs = File::Spec->splitdir( $directories );
    my @these_dirs = ();
    
    foreach(@dirs) {
        push @these_dirs,$_;
        my $dir = File::Spec->catpath( $volume, File::Spec->catfile( @these_dirs, $file), $file);
        
        if (!-d $dir) {
            print "Making Directory $dir\n";
            mkdir($dir) || return 0;
        }
    }
    
    return 1;
}

sub num_of_month($) {
    my ($text_month) = @_;
    if ($text_month =~ /Jan/)   {return 0;}
    if ($text_month =~ /Feb/)   {return 1;}
    if ($text_month =~ /March/) {return 2;}
    if ($text_month =~ /April/) {return 3;}
    if ($text_month =~ /May/)   {return 4;}
    if ($text_month =~ /June/)  {return 5;}
    if ($text_month =~ /July/)  {return 6;}
    if ($text_month =~ /Aug/)   {return 7;}
    if ($text_month =~ /Sept/)  {return 8;}
    if ($text_month =~ /Oct/)   {return 9;}
    if ($text_month =~ /Nov/)   {return 10;}
    if ($text_month =~ /Dec/)   {return 11;}
}

sub boundschecking() {
    my ($value) = @_;
    
    if ($value >= 1) {$value = 1;}
    # if ($value == 0) {$value = FAILED;}
    
    return ($value);
}

sub WriteoutQuake($) {
    my ($counter) = @_;
    my $recounter = 0;
    
    if ($counter != FAILED) {
        my $openfile = Earthquake;
        
        open (MF, ">$quake_marker_file");
        &file_header($openfile);
        
        while ($recounter < $counter) {
            $date = $quakedata[$recounter]->{'date'};
            $time = $quakedata[$recounter]->{'time'};
            $lat = $quakedata[$recounter]->{'lat'};
            $lat  = sprintf("% 7.2f",$lat);
            $long = $quakedata[$recounter]->{'long'};
            $long = sprintf("% 7.2f",$long);
            $dep = $quakedata[$recounter]->{'dep'};
            $dep = sprintf("% 6.1f",$dep);
            $mag = $quakedata[$recounter]->{'mag'};
            $mag = sprintf("%-3s",$mag);
            $mag = sprintf("%.1f",$mag);
            $q = $quakedata[$recounter]->{'q'};
            $q  = sprintf("%-2s",$q);
            $detail = $quakedata[$recounter]->{'detail'};
            
            if ($detail =~ /&#060;/) {
                substr ($detail,0,6) = "<";
            }
            
            $detail = sprintf("%-17s",''.$detail.'');
            
            if ($mag >= $quakesettings->{'QuakeMinimumSize'}) {
                if ($quakesettings->{'QuakeImageList'} =~ /\w/) {
                    print MF "$lat $long \"\" image=$quakesettings->{'QuakeImageList'} color=".colourisemag($mag)."";
                    if ($quakesettings->{'QuakeImageTransparent'} =~ /\d/) {
                        print MF " transparent=$quakesettings->{'QuakeImageTransparent'}";
                    }
                    
            		print MF "\n";
                }
                else {
                    print MF "$lat $long \"\" color=".colourisemag($mag)." symbolsize=".drawcircle($mag)."\n";
                }
                
            	if ($quakesettings->{'QuakeDetailList'} =~ /\w/) {
                    my $tmp1 = $quakesettings->{'QuakeDetailList'};
                    $tmp1 =~ s/<date>/$date/g;
                    $tmp1 =~ s/<time>/$time/g;
                    $tmp1 =~ s/<lat>/$lat/g;
                    $tmp1 =~ s/<long>/$long/g;
                    $tmp1 =~ s/<depth>/$dep/g;
                    $tmp1 =~ s/<mag>/$mag/g;
                    $tmp1 =~ s/<quality>/$q/g;
                    $tmp1 =~ s/<location>/$detail/g;
                    print MF "$lat $long \"$tmp1\" color=".colourisetext($mag)." align=$quakesettings->{'QuakeDetailAlign'}\n";
                }
            }
            
            $recounter++;
        }
    }
}

sub get_Correct_quake_Feed() {
    if ($quakesettings->{'QuakeReportingDuration'} =~ /day/i) {
        if ($quakesettings->{'QuakeReportingSize'} =~ /significant/i) {
            $quake_location = $quake_location_CSV_24H_SIG;
        } elsif ($quakesettings->{'QuakeReportingSize'} =~ /4.5/i) {
            $quake_location = $quake_location_CSV_24H_45;
        } elsif ($quakesettings->{'QuakeReportingSize'} =~ /2.5/i) {
            $quake_location = $quake_location_CSV_24H_25;
        } elsif ($quakesettings->{'QuakeReportingSize'} =~ /1.0/i) {
            $quake_location = $quake_location_CSV_24H_10;
        } else {
            $quake_location = $quake_location_CSV_24H_ALL;
        }
    } elsif ($quakesettings->{'QuakeReportingDuration'} =~ /week/i) {
        if ($quakesettings->{'QuakeReportingSize'} =~ /significant/i) {
            $quake_location = $quake_location_CSV_7D_SIG;
        } elsif ($quakesettings->{'QuakeReportingSize'} =~ /4.5/i) {
            $quake_location = $quake_location_CSV_7D_45;
        } elsif ($quakesettings->{'QuakeReportingSize'} =~ /2.5/i) {
            $quake_location = $quake_location_CSV_7D_25;
        } elsif ($quakesettings->{'QuakeReportingSize'} =~ /1.0/i) {
            $quake_location = $quake_location_CSV_7D_10;
        } else {
            $quake_location = $quake_location_CSV_7D_ALL;
        }
	} elsif ($quakesettings->{'QuakeReportingDuration'} =~ /month/i) {
        if ($quakesettings->{'QuakeReportingSize'} =~ /significant/i) {
            $quake_location = $quake_location_CSV_30D_SIG;
        } elsif ($quakesettings->{'QuakeReportingSize'} =~ /4.5/i) {
            $quake_location = $quake_location_CSV_30D_45;
        } elsif ($quakesettings->{'QuakeReportingSize'} =~ /2.5/i) {
            $quake_location = $quake_location_CSV_30D_25;
        } elsif ($quakesettings->{'QuakeReportingSize'} =~ /1.0/i) {
            $quake_location = $quake_location_CSV_30D_10;
        } else {
            $quake_location = $quake_location_CSV_30D_ALL;
		}
	}
}

sub get_quakedata() {
    my $quaketxt;
    my $counter = 0;
    
    $quaketxt=get_webpage($quake_location);
    
    if ($quaketxt !~ /FAILED/) {
        # print $quaketxt;
        if ($quaketxt) {
            foreach (split("\n",$quaketxt)) {
                    #time,latitude,longitude,depth,mag,magType,nst,gap,dmin,rms,net,id,updated,place,type,horizontalError,depthError,magError,magNst,status,locationSource,magSource
                #2016-11-22T08:52:44.920Z,38.7886658,-122.7630005,0.9,0.94,md,8,107,0.01999,0.02,nc,nc72728310,2016-11-22T09:08:02.745Z,"1km NNW of The Geysers, California",earthquake,0.55,1.16,0.06,4,automatic,nc,nc
                
                #print "$_\n";
                if (/(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2}).\d+Z,([\d\-\.]+),([\d\-\.]+),([\d\.]+),([\d\.]+),([\w\d\.\-\"\:]+),([\w\d\.\-\"\:]*),([\w\d\.\-\"\:]+),([\w\d\.\-\"\:]+),([\w\d\.\-\"\:]+),([\w\d\.\-\"\:]+),([\w\d\.\-\"\:]+),([\w\d\.\-\"\:]+),\"([\w\W\d\.\s\,\:]+)\",([\w\d\.\-\"\:]+),([\w\d\.\-\"\:]+),([\w\d\.\-\"\:]+),([\w\d\.\-\"\:]+),([\w\d\.\-\"\:]+),([\w\d\.\-\"\:]+),([\w\d\.\-\"\:]+),([\w\d\.\-\"\:]+)/) {
                    my ($date,$time,$lat,$long,$dep,$mag,$magType,$nst,$gap,$dmin,$rms,$net,$id,$updated,$place,$type,$horizontalError,$depthError,$magError,$magNst,$status,$location,$magSource)=($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23);
                    #print "1=$1,2=$2,3=$3,4=$4,5=$5,6=$6,7=$7,8=$8,9=$9,10=$10,11=$11,12=$12,13=$13,14=$14,15=$15,16=$16,17=$17,18=$18,19=$19,20=$20,21=$21,22=$22,23=$23\n";
                    #print "DATE = $date, TIME = $time, LAT = $lat, LONG = $long, DEPTH = $dep, MAGITUDE = $mag, LOCATION = $place, CAUSE = $type\n";
                    
                    push @quakedata, {
                        'date'   => $date,
                        'time'   => $time,
                        'lat'    => $lat,
                        'long'   => $long,
                        'dep'    => $dep,
                        'mag'    => $mag,
                        'detail' => $place,
                        'q'      => $type,
                    };
                    
                    # print "$time, $date, $lat, $long, $dep, $mag, $place, $type.\n";
                    $counter++;
                }
                # else {print "failed\n";}
            }
        }
        
        my $recounter = 0;
        
        while ($recounter < $counter) {
            my $lat1 = $quakedata[$recounter]->{'lat'};
            my $long1= $quakedata[$recounter]->{'long'};
            
            $lat1 *= 1;
            $long1 *= 1;
            $quakedata[$recounter]->{'lat'}  = $lat1;
            $quakedata[$recounter]->{'long'} = $long1;
            $quakedata[$recounter]->{'mag'} =~ s/M$//;
            $quakedata[$recounter]->{'mag'} *= 1;
            $quakedata[$recounter]->{'dep'} *= 1;
            my $q1 = $quakedata[$recounter]->{'q'};
            if ($q1 != A && $q1 != B) {$q = "U";}
            $quakedata[$recounter]->{'q'} = $q1;
            $recounter++;
        }
        
        print "  Updated earthquake information\n";
        
        return $counter;
    }
    else {
        print "  WARNING... unable to access or download updated earthquake information\n";
        
        return $quaketxt;
    }
}

#my $storm_base_location = "http://www.nrlmry.navy.mil/tcdat/sectors/ftp_sector_file";
#my $storm_past_location = "http://www.nrlmry.navy.mil/archdat/test/kml/TC/2011/ATL/12L/trackfile.txt";
#my $storm_future_location = "http://www.nrlmry.navy.mil/atcf_web/docs/current_storms/al122011.tcw";

sub get_hurricanearcdata($) {
    my ($counter) = @_;
    my $recounter = 0;
    my $forcounter = 0;
    my $actcounter = 0;
    my $storm_track;
    my $temp_chop;
    
    # print "Counter=".$counter."\n";
    if ($counter != FAILED) {
        while ($recounter < $counter) {
            # Get Past Locations
            $storm_past = get_webpage($storm_past_location.$hurricanedata[$recounter]->{'year'}."/".$hurricanedata[$recounter]->{'loc'}."/".$hurricanedata[$recounter]->{'code'}."/trackfile.txt");
            # print $storm_past;
            
            if ($storm_track !~ /FAILED/) {
                foreach (split("\n",$storm_past)) {
                    if (/([\d\w]+)\s(\w+)\s(\d+)\s(\d+)\s+([\d\-\.NS]+)\s+([\d\-\.EW]+)\s(\w+)\s+(\d+)\s+(\d+)/) {
                        my($code,$name,$date,$time,$lat,$long,$location,$speed,$detail)=($1,$2,$3,$4,$5,$6,$7,$8,$9);
                        
                        # print "$name, $lat, $long, $date, $time, $location, $speed, $code, $ocean, $previous_name\n";
                        if ($lat =~ /(\d+\.\d+)([NS])/) {
                            ($lat,$sign)=($1,$2);
                            $lat *= -1 if $sign =~ /s/i;
                        }
                        $lat *= 1;
                        
                        if ($long =~ /(\d+\.\d+)([WE])/) {
                            ($long,$sign)=($1,$2);
                            $long *= -1 if $sign =~ /w/i;
                        }
                        
                        $long *= 1;
                        
                        # print "$name, $lat, $long, $date, $time, $location, $speed, $code, $ocean, $previous_name\n";
                        # print "$recounter, $lat, $long, $name, $actcounter\n";
                        
                        push @hurricanearcdataact, {
                            'num'   => $recounter,
                            'lat'   => $lat,
                            'long'  => $long,
                            'name'	=> $name,
                        };
                        
                        $actcounter++;
					}
                }
            }
            
            $recounter++;
        }
        
        $recounter = 0;
        while ($recounter < $counter) {
            # Get Future Locations
            $temp_chop = chop($hurricanedata[$recounter]->{'code'});
            $temp_chop = $storm_future_location.$hurricanedata[$recounter]->{'ocean'}.$hurricanedata[$recounter]->{'code'}.$hurricanedata[$recounter]->{'year'}.".tcw\n";
            #print $temp_chop."\n";
            $storm_track = get_webpage($temp_chop);
            #print $storm_track;
            
            if ($storm_track !~ /FAILED/) {
                foreach (split("\n",$storm_track)) {
                    #print "#-".$_."\n";
                    # [T][0-9]+ [0-9]+[NS] [0-9]+[EW] [0-9]+
                    if (/(T\d{3})\s(\d{3,4}\w)\s(\d{3,4}\w)\s\d{3}/) {
                        my($time,$lat,$long)=($1,$2,$3);
                        #print "$time, $lat, $long,";
                        
                        if ($lat =~ /(\d+)([NS])/) {
                            ($lat,$sign)=($1,$2);
                            $lat *= -1 if $sign =~ /s/i;
                        }
                        $lat *= 0.1;
                        
                        if ($long =~ /(\d+)([WE])/) {
                            ($long,$sign)=($1,$2);
                            $long *= -1 if $sign =~ /w/i;
                        }
                        $long *= 0.1;
                        #print "$recounter, $lat, $long\n";
                        
                        push @hurricanearcdatafor, {
                            'num'   => $recounter,
                            'lat'   => $lat,
                            'long'  => $long,
                        };
                        
                        $forcounter++;
                    }
                }
            }
        
        $recounter++;
        }
        
        print "  Updated storm arc information\n";
    }
    else {
        $actcounter = FAILED;
        $forcounter = FAILED;
        print "  WARNING... unable to access or download updated storm arc information\n";
    }
    
    return $actcounter,$forcounter;
}

sub get_hurricanedata() {
    my $counter = 0;
    my $hurricanetxt;
    my $sign;
    my $year;
    
    $hurricanetotallist = get_webpage($storm_base_location);
    # print $hurricanetotallist;
    
    if ($hurricanetxt !~ /FAILED/) {
        foreach (split("\n",$hurricanetotallist)) {
            if (/([\d\w]+)\s(\w+)\s(\d+)\s(\d+)\s+([\d\-\.NS]+)\s+([\d\-\.EW]+)\s(\w+)\s+(\d+)\s+(\d+)/) {
                my($code,$name,$date,$time,$lat,$long,$location,$speed,$detail)=($1,$2,$3,$4,$5,$6,$7,$8,$9);
                if ($lat =~ /(\d+\.\d+)([NS])/) {
                    ($lat,$sign)=($1,$2);
                    $lat *= -1 if $sign =~ /s/i;
                }
                $lat *= 1;
                
                if ($long =~ /(\d+\.\d+)([WE])/) {
                    ($long,$sign)=($1,$2);
                    $long *= -1 if $sign =~ /w/i;
                }
                $long *= 1;
                $speed =~ s/^0+//;
                
                if ($name =~ /INVEST/) {
                    $type = "DEP";
                    $name = $code;
                }
                else {
                    $type = "STO";
                }
                
                $year = "20".substr $date,0,2;
                
                if ($location =~ /ATL/) {
                    $ocean = "al";
                }
                elsif ($location =~ /WPAC/) {
                    $ocean = "wp";
                }
                elsif ($location =~ /EPAC/) {
                    $ocean = "ep";
                }
                elsif ($location =~ /CPAC/) {
                    $ocean = "cp";
                }
                
                push @hurricanedata, {
                    'type'  => $type,
                    'file'  => $file,
                    'name'  => $name,
                    'lat'   => $lat,
                    'long'  => $long,
                    'speed' => $speed,
                    'code'  => $code,
                    'year'  => $year,
                    'ocean' => $ocean,
                    'loc'   => $location,
                };
                #print "$type, $name, $lat, $long, $date, $time, $location, $speed, $code, $year, $ocean\n";
            }
            
            $counter++;
        }
        
        if ($counter == 0) {
            print "  ERROR (-1)?... Unable to parse storm information\n";
            return -1;
        }
        else {
            print "  Updated storm information\n";
            return $counter;
        }
    }
    else {
        print "  WARNING... unable to access or download updated storm information\n";
        return $hurricanetxt;
    }
}

sub WriteoutHurricaneArc() {
    my ($numhur,$numact,$numfor) = @_;
    my $counter = 0;
    my $recounter = 0;
    
    if ($numhur =~ /FAILED/) {}
    elsif ($numact =~ /FAILED/) {}
    elsif ($numfor =~ /FAILED/) {}
    else {
        my $openfile = "Hurricane Arc File";
        
        open (MF, ">$hurricane_arc_file");
        &file_header($openfile);
        print MF "#\n#Thanks to Hans Ecke <http://hans.ecke.ws/xplanet> for his idea of using GreatArcs to put in the storm tracks\n\n";
        if ($stormsettings->{'StormTrackOnOff'} =~ /On/) {
            while ($counter < $numact) {
                if ($hurricanearcdataact[$counter]->{'num'} ne $hurricanearcdataact[($counter+1)]->{'num'}) {
                    #printf MF "%.1f %.1f %.1f %.1f color=$stormsettings->{'StormColorTrackReal'}\n", $hurricanearcdataact[$counter]->{'lat'}, $hurricanearcdataact[$counter]->{'long'},$hurricanedata[$recounter]->{'lat'}, $hurricanedata[$recounter]->{'long'};
                    $recounter++;
                    print MF "\# $hurricanearcdataact[$counter]->{'name'}\n\n";
                }
                elsif ($hurricanearcdataact[$counter]->{'num'} eq $hurricanearcdataact[($counter+1)]->{'num'}) {
                    if ( ($hurricanearcdataact[$counter]->{'lat'} -  $hurricanearcdataact[$counter+1]->{'lat'} > 10) || ($hurricanearcdataact[$counter]->{'lat'} -  $hurricanearcdataact[$counter+1]->{'lat'} < -10) || ($hurricanearcdataact[$counter]->{'long'} -  $hurricanearcdataact[$counter+1]->{'long'} > 10) || ($hurricanearcdataact[$counter]->{'long'} -  $hurricanearcdataact[$counter+1]->{'long'} < -10)) {
                    }
                    else {
                        printf MF "%.1f %.1f %.1f %.1f color=$stormsettings->{'StormColorTrackReal'}\n", $hurricanearcdataact[$counter]->{'lat'}, $hurricanearcdataact[$counter]->{'long'}, $hurricanearcdataact[($counter+1)]->{'lat'}, $hurricanearcdataact[($counter+1)]->{'long'};
                    }
                }
                else {
                    print MF "\n\n";
                }
                
                $counter++;
            }
            
            $counter = 0;
            $recounter = 0;
            while ($counter < $numfor) {
                if ($hurricanearcdatafor[$counter]->{'num'} ne $hurricanearcdatafor[($counter-1)]->{'num'}) {
                    #printf MF "%.1f %.1f %.1f %.1f color=$stormsettings->{'StormColorTrackPrediction'}\n", $hurricanedata[$recounter]->{'lat'}, $hurricanedata[$recounter]->{'long'},$hurricanearcdatafor[$counter]->{'lat'}, $hurricanearcdatafor[$counter]->{'long'};
                    $recounter++;
                }
                
                if ($hurricanearcdatafor[$counter]->{'num'} eq $hurricanearcdatafor[($counter+1)]->{'num'}) {
                    printf MF "%.1f %.1f %.1f %.1f color=$stormsettings->{'StormColorTrackPrediction'}\n", $hurricanearcdatafor[$counter]->{'lat'}, $hurricanearcdatafor[$counter]->{'long'}, $hurricanearcdatafor[($counter+1)]->{'lat'}, $hurricanearcdatafor[($counter+1)]->{'long'};
                }
                else {
                    print MF "\n\n";
                }
                
                $counter++;
            }
        }
    
    close MF;
    }
}

sub WriteoutHurricane($) {
    my ($counter) = @_;
    my $recounter = 0;
    
    if ($counter !~ /FAILED/) {
        my $openfile = Hurricane;
        
        open (MF, ">$hurricane_marker_file");
        &file_header($openfile);
        while ($recounter < $counter) {
            $type = $hurricanedata[$recounter]->{'type'};
            $lat = $hurricanedata[$recounter]->{'lat'};
            $lat  = sprintf("% 7.2f",$lat);
            $long = $hurricanedata[$recounter]->{'long'};
            $long = sprintf("% 7.2f",$long);
            $name = $hurricanedata[$recounter]->{'name'};
            $speed = $hurricanedata[$recounter]->{'speed'};
            #print "Speed=$speed\n";
            $speed = sprintf("% 3.0f",$speed);
            #print "Speed=$speed\n";
            $file = $hurricanedata[$recounter]->{'file'};
            $file = sprintf("%-17s",'"'.$file.'"');
            
            if ($stormsettings->{'StormNameOnOff'} =~ /On/) {
                print MF "$lat $long \"$name\" align=$stormsettings->{'StormAlignName'} color=$stormsettings->{'StormColorName'}";
                
                if ($stormsettings->{'StormImageList'} =~ /\w/) {
                    print MF " image=$stormsettings->{'StormImageList'}";
                    
                    if ($stormsettings->{'StormImageTransparent'} =~ /\w/) {
                        print MF " transparent=$stormsettings->{'StormImageTransparent'}";
                    }
                }
                print MF "\n";
            }
            
            if ($stormsettings->{'StormDetailList'} =~ /\w/) {
                my $tmp1 = $stormsettings->{'StormDetailList'};
                
                $tmp1 =~ s/<lat>/$lat/g;
                $tmp1 =~ s/<long>/$long/g;
                $tmp1 =~ s/<type>/$type/g;
                $tmp1 =~ s/<name>/$name/g;
                $tmp1 =~ s/<speed>/$speed/g;
                #print "Speed=$speed\n";
                #print "$lat $long \"$tmp1\" align=$stormsettings->{'StormAlignDetail'} color=$stormsettings->{'StormColorDetail'}\n";
                print MF "$lat $long \"$tmp1\" align=$stormsettings->{'StormAlignDetail'} color=$stormsettings->{'StormColorDetail'}";
            }
            
            if ($stormsettings->{'StormImageList'} =~ /\w/) {
                print MF " image=$stormsettings->{'StormImageList'}";
                if ($stormsettings->{'StormImageTransparent'} =~ /\w/) {
                    print MF " transparent=$stormsettings->{'StormImageTransparent'}";
                }
            }
            
            print MF "\n";
            $recounter++;
        }
        
        close MF;
    }
}

sub install_marker() {
    my ($version,$type) = @_;
    
    print "install_marker\nVersion = $version\nType = $type\n";
    open (MF, "<$winXPlanetBG");
    
    my $counter = 1;
    my $recounter = 1;
    
    #read in ini file
    while (<MF>)  {
        s/\n//;
        ($inilines[$counter], $inivalue[$counter]) = split ("=");
        $counter ++;
    }
    
    close (MF);
    
    #write out backup file.
    open (MF, ">$winxplanetbgbackup");
    while ($recounter < $counter) {
        print MF "$inilines[$counter]=$inivalue[$counter]\n";
        $recounter++;
    }
    
    $recounter = 1;
    if ($type =~ /cloud/) {
        open (MF, ">$cloudbatch");
        print MF "\@echo off\ntotalmarker.exe -clouds\n";
        close MF;
        
        while ($recounter < $counter) {
            #Execute File after download=1
            #File after download=C:\Xplanet\updateclouds.bat
            if ($inilines[$recounter] =~ /Execute File after download/) {
                $inivalue[$recounter] = 1;
            }
            
            if ($inilines[$recounter] =~ /File after download/) {
                $inivalue[$recounter] = $cloudbatch;
            }
            
            $recounter++;
        }
        
        $recounter = 1;
    }
    elsif ($version <= $oldversionnumber) {
        print "old version\n";
    }
    else {
        print "The New version isn't out of beta and isn't supported here yet.\n";
    }
    
    open (MF, ">$winXPlanetBG");
    $recounter = 1;
    
    #Write the new .ini file
    while ($recounter < $counter) {
        print MF "$inilines[$recounter]=$inivalue[$recounter]\n";
        $recounter++;
    }
}

sub install() {
    my ($flag) =@_;
    
    $oldversionnumber = 0.94;
    $newversionnumber = 0.95;
    if ($flag =~ /eclipsfile/) {
        my $test = &make_directory($xplanet_config_dir);
        
        if ($test == 0) {
            print "Can't write settings file, directory xplanet/config does exist and can't be created.\n";
            exit 1;
            die;
        }
        
        if (-e $eclipse_old_data_file) {
            copy ("$eclipse_old_data_file","$eclipse_data_file");
            unlink $eclipse_old_data_file;
        }
        else {
            &get_eclipsedata;
        }
        
        &get_it_right_lamer;
    }
    elsif ($flag =~ /configfile/) {
        my $test = &make_directory($xplanet_config_dir);
        
        if ($test == 0) {
            print "Can't write settings file, directory xplanet/config does exist and can't be created.\n";
            exit 1;
            die;
        }
        
        if (-e $settings_old_ini_file) {
            copy ("$settings_old_ini_file","$settings_ini_file");
            unlink $settings_old_ini_file;
        }
        else {
            print "\nInstalling Files Needed to Run\n";
            open (MF, ">$settings_ini_file");
            print MF "\#Totalmarker ini file\n\#\n\#Leaving the options blank will make the option unused.\n\#See http://www.wizabit.eclipse.co.uk/xplanet/pages/TotalMarker.html for details of this file\n#Config File Written by TotalMarker version $VERSION\n";
            print MF "\#\n\#QUAKE\n\#\nQuakeDetailColorMin=Green\nQuakeDetailColorInt=Yellow\nQuakeDetailColorMax=Red\nQuakeDetailAlign=Above\nQuakeCircleColor=Multi\nQuakePixelMax=\nQuakePixelMin=\nQuakePixelFactor=1\nQuakeImageList=\nQuakeImageTransparent=\nQuakeDetailList=<mag>\nQuakeDetailColor=Multi\nQuakeMinimumSize=0\n";
            print MF "\#\n\#VOLCANO\n\#\nVolcanoCircleSizeInner=4\nVolcanoCircleSizeMiddle=8\nVolcanoCircleSizeOuter=12\nVolcanoCircleColorInner=Yellow\nVolcanoCircleColorMiddle=Red\nVolcanoCircleColorOuter=Brown\nVolcanoNameOnOff=On\nVolcanoNameColor=Brown\nVolcanoNameAlign=Below\nVolcanoImageList=\nVolcanoImageTransparent=\nVolcanoDetailList=\nVolcanoDetailAlign=\nVolcanoDetailColor=\n";
            print MF "\#\n#STORMS\n\#\nStormColorTrackReal=Blue\nStormColorTrackPrediction=SkyBlue\nStormNameOnOff=On\nStormColorName=SkyBlue\nStormAlignName=Above\nStormDetailList=<type>\nStormColorDetail=SkyBlue\nStormAlignDetail=Below\nStormImageList=\nStormImageTransparent=\nStormTrackOnOff=On\n";
            print MF "\#\n\#ECLIPSE\n\#\nEclipseOnOff=On\nEclipseNotifyOnOff=On\nEclipseNotifyTimeHours=48\n";
            print MF "\#\n\#NORAD\n\#\nNoradIssImage=iss.png\nNoradIssText=\nNoradIssDetail=transparent={0,0,0} trail={orbit,-5,0,5} color=yellow altcirc=0 trail={orbit,-10,0,5}\nNoradIssOnOff=On\nNoradHstImage=hst.png\nNoradHstText=\nNoradHstDetail=transparent={0,0,0}\nNoradHstOnOff=On\nNoradSoyuzImage=Soyuz.png\nNoradSoyuzText=\nNoradSoyuzDetail=transparent={0,0,0}\nNoradSoyuzOnOff=On\nNoradStsImage=sts.png\nNoradStsText=\nNoradStsDetail=transparent={0,0,0}\nNoradStsOnOff=On\nNoradSatImage=sat.png\nNoradSatText=\nNoradSatDetail=transparent={0,0,0}\nNoradSatOnOff=On\nNoradMiscOnOff=Off\nNoradTleNumbers=\nNoradMiscDetail=\nNoradFileName=tm\n";
            print MF "\#\n\#LABELUPDATE\n\#\nLabelOnOff=On\nLabelWarningQuake=84600\nLabelWarningVolcano=604800\nLabelWarningStorm=86400\nLabelWarningNorad=604800\nLabelWarningCloud=21600\nLabelColorOk=Green\nLabelColorWarn=Yellow\nLabelColorError=Red\n";
            close MF;
            &update_ini_file;
            print "Done!\n";
        }
        
        &get_it_right_lamer;
    }
    elsif ($flag =~ /storm/) {
        my $xplanetversion = &get_program_version();
        
        if ($xplanetversion =~ /(\d.\d\d)(\w)/) {
            my ($pversion,$prevision) = ($1,$2);
            
            $pversion *= 1;
            if ($pversion < 0.95) {
                &install_marker($oldversionnumber,$flag);
            }
            else {
                &install_marker($newversionnumber,$flag);
            }
            
            print "Storm\nXplanet Version = $pversion, Revision = $prevision:\n";
        }
    }
    elsif ($flag =~ /quake/) {
        my $xplanetversion = &get_program_version();
        
        if ($xplanetversion =~ /(\d.\d\d)(\w)/) {
            my ($pversion,$prevision) = ($1,$2);
            
            $pversion *= 1;
            if ($pversion < 0.93) {
                print "The Version of Xplanet won't support Earthquakes, please Upgrade to 0.93d or better\n";
            }
            elsif ($pversion = 0.93) {
                if (ord $prevision < ord d) {
                    print "The Version of Xplanet won't support Earthquakes, please Upgrade to 0.93d or better\n";
                }
            }
            elsif ($pversion < 0.95 ) {
                &install_marker($oldversionnumber,$flag);
            }
            else {
                &install_marker($newversionnumber,$flag);
            }
            
            print "Earthquakes\nXplanet Version = $pversion, Revision = $prevision:\n";
        }
    }
    elsif ($flag =~ /norad/) {
        my $xplanetversion = &get_program_version();
        
        if ($xplanetversion =~ /(\d.\d\d)(\w)/) {
            my ($pversion,$prevision) = ($1,$2);
            
            $pversion *= 1;
            if ($pversion < 0.95) {
                &install_marker($oldversionnumber,$flag);
            }
            else {
                &install_marker($newversionnumber,$flag);
            }
            
            print "NORAD\nXplanet Version = $pversion, Revision = $prevision:\n";
        }
    }
    elsif ($flag =~ /cloud/) {
        if (-e $winXPlanetBG) {
            &install_marker($newversionnumber,$flag);
        }
        else {
            print "winXPlanetBG not Found\nStopping\nTo Install Clouds winXPlanetBG must be installed\n";
            exit 1;
            die;
        }
        
        print "Clouds\n";
    }
    elsif ($flag =~ /volcano/) {
        my $xplanetversion = &get_program_version();
        
        if ($xplanetversion =~ /(\d.\d\d)(\w)/) {
            my ($pversion,$prevision) = ($1,$2);
            
            $pversion *= 1;
            if ($pversion < 0.95) {
                &install_marker($oldversionnumber,$flag);
            }
            else {
                &install_marker($newversionnumber,$flag);
            }
            
            print "Volcano\nXplanet Version = $pversion, Revision = $prevision:\n";
        }
    }
    elsif ($flag =~ /eclipse/) {
        my $xplanetversion = &get_program_version();
        
        if ($xplanetversion =~ /(\d.\d\d)(\w)/) {
            my ($pversion,$prevision) = ($1,$2);
            
            $pversion *= 1;
            if ($pversion < 0.95) {
                &install_marker($oldversionnumber,$flag);
            }
            else {
                &install_marker($newversionnumber,$flag);
            }
            
            print "Eclipse\nXplanet Version = $pversion, Revision = $prevision:\n";
        }
    }
    elsif ($flag =~ /updatelabel/) {
        my $xplanetversion = &get_program_version();
        
        if ($xplanetversion =~ /(\d.\d\d)(\w)/) {
            my ($pversion,$prevision) = ($1,$2);
            
            $pversion *= 1;
            if ($pversion < 0.95) {
                &install_marker($oldversionnumber,$flag);
            }
            else {
                &install_marker($newversionnumber,$flag);
            }
            
            print "UpdateLabel\nXplanet Version = $pversion, Revision = $prevision:\n";
        }
    }
    elsif ($flag =~ /totalmarker/) {
        my $oldversion = "1.03.1";
        my $xplanetversion = &get_program_version();
        my $result = shift @ARGV;
        
        if ($result =~ /Update/ || $result =~ /update/ || $result =~ /patch/ || $result =~ /Patch/) {
            print "Updating TotalMarker Settings to $VERSION settings.\n";
            print "xplanet = $xplanetversion\;totalmarker\n";
            &update_ini_file;
        }
        else {
            open (MF, "<$settings_ini_file");
            while (<MF>) {
                foreach (split "\n") {
                    if ($_ =~ /Config File Written by/) {
                        my $tmp1,$tmp2,$tmp3,$tmp4,$tmp5,$tmp6,$tmp7 = split " ";
                        
                        $oldversion = $tmp7;
                    }
                }
                
                close MF;
                &changelog_print ($oldversion);
            }
        }
    }
    
    $installed = 1;
}

sub update_ini_file() {
    &get_settings;
    print "\nUpgrading Totalmarker.ini File to Latest Version.\n";
    open (MF, ">$settings_ini_file");
    print MF "\#Totalmarker ini file\n\#\n\#Leaving the options blank will make the option unused.\n\#See http://www.wizabit.eclipse.co.uk/xplanet/pages/TotalMarker.html for details of this file\n#Config File Written by TotalMarker version $VERSION\n";
    
    # QUAKE
    print MF "\#\n\#QUAKE\n\#\nQuakeDetailColorMin=";
    if ($quakesettings->{'QuakeDetailColorMin'} =~ /\w/)                        {print MF "$quakesettings->{'QuakeDetailColorMin'}";}
    else {print MF "Green";}
    
    print MF "\nQuakeDetailColorInt=";
    if ($quakesettings->{'QuakeDetailColorInt'} =~ /\w/)                        {print MF "$quakesettings->{'QuakeDetailColorInt'}";}
    else {print MF "Yellow";}
    
    print MF "\nQuakeDetailColorMax=";
    if ($quakesettings->{'QuakeDetailColorMax'} =~ /\w/)                        {print MF "$quakesettings->{'QuakeDetailColorMax'}";}
    else {print MF "Red";}
    
    print MF "\nQuakeDetailAlign=";
    if ($quakesettings->{'QuakeDetailAlign'} =~ /\w/)                           {print MF "$quakesettings->{'QuakeDetailAlign'}";}
    else {print MF "Above";}
    
    print MF "\nQuakeCircleColor=";
    if ($quakesettings->{'QuakeCircleColor'} =~ /\w/)                           {print MF "$quakesettings->{'QuakeCircleColor'}";}
    else {print MF "Multi";}
    
    print MF "\nQuakePixelMax=";
    if ($quakesettings->{'QuakePixelMax'} =~ /\w/)                              {print MF "$quakesettings->{'QuakePixelMax'}";}
    else {print MF "";}
    
    print MF "\nQuakePixelMin=";
    if ($quakesettings->{'QuakePixelMin'} =~ /\w/)                              {print MF "$quakesettings->{'QuakePixelMin'}";}
    else {print MF "";}
    
    print MF "\nQuakePixelFactor=";
    if ($quakesettings->{'QuakePixelFactor'} =~ /\w/)                           {print MF "$quakesettings->{'QuakePixelFactor'}";}
    else {print MF "1";}
    
    print MF "\nQuakeImageList=";
    if ($quakesettings->{'QuakeImageList'} =~ /\w/)                             {print MF "$quakesettings->{'QuakeImageList'}";}
    else {print MF "";}
    
    print MF "\nQuakeImageTransparent=";
    if ($quakesettings->{'QuakeImageTransparent'} =~ /\w/)                      {print MF "$quakesettings->{'QuakeImageTransparent'}";}
    else {print MF "";}
    
    print MF "\nQuakeDetailList=";
    if ($quakesettings->{'QuakeDetailList'} =~ /\w/)                            {print MF "$quakesettings->{'QuakeDetailList'}";}
    else {print MF "<mag>";}
    
    print MF "\nQuakeDetailColor=";
    if ($quakesettings->{'QuakeDetailColour'} =~ /\w/)                          {print MF "$quakesettings->{'QuakeDetailColour'}";}
    else {print MF "Multi";}
    
    print MF "\nQuakeMinimumSize=";
    if ($quakesettings->{'QuakeMinimumSize'} =~ /\w/)                           {print MF "$quakesettings->{'QuakeMinimumSize'}";}
    else {print MF "0";}
    
    print MF "\nQuakeReportingDuration=";
    if ($quakesettings->{'QuakeReportingDuration'} =~ /\w/)                     {print MF "$quakesettings->{'QuakeReportingDuration'}";}
    else {print MF "Week";}
    
    print MF "\nQuakeReportingSize=";
    if ($quakesettings->{'QuakeReportingSize'} =~ /\w/)                         {print MF "$quakesettings->{'QuakeReportingSize'}";}
    else {print MF "All";}
    
    print MF "\nQuakeFade=";
    if ($quakesettings->{'QuakeFade'} =~ /\w/)                                  {print MF "$quakesettings->{'QuakeFade'}";}
    else {print MF "On";}
    
    # VOLCANO
    print MF "\n\#\n\#VOLCANO\n\#";
    
    print MF "\nVolcanoCircleSizeInner=";
    if ($volcanosettings->{'VolcanoCircleSizeInner'} =~ /\w/)                   {print MF "$volcanosettings->{'VolcanoCircleSizeInner'}";}
    else {print MF "4";}
    
    print MF "\nVolcanoCircleSizeMiddle=";
    if ($volcanosettings->{'VolcanoCircleSizeMiddle'} =~ /\w/)                  {print MF "$volcanosettings->{'VolcanoCircleSizeMiddle'}";}
    else {print MF "8";}
    
    print MF "\nVolcanoCircleSizeOuter=";
    if ($volcanosettings->{'VolcanoCircleSizeOuter'} =~ /\w/)                   {print MF "$volcanosettings->{'VolcanoCircleSizeOuter'}";}
    else {print MF "12";}
    
    print MF "\nVolcanoCircleColorInner=";
    if ($volcanosettings->{'VolcanoCircleColorInner'} =~ /\w/)                  {print MF "$volcanosettings->{'VolcanoCircleColorInner'}";}
    else {print MF "Yellow";}
    
    print MF "\nVolcanoCircleColorMiddle=";
    if ($volcanosettings->{'VolcanoCircleColorMiddle'} =~ /\w/)                 {print MF "$volcanosettings->{'VolcanoCircleColorMiddle'}";}
    else {print MF "Red";}
    
    print MF "\nVolcanoCircleColorOuter=";
    if ($volcanosettings->{'VolcanoCircleColorOuter'} =~ /\w/)                  {print MF "$volcanosettings->{'VolcanoCircleColorOuter'}";}
    else {print MF "Brown";}
    
    print MF "\nVolcanoNameOnOff=";
    if ($volcanosettings->{'VolcanoNameOnOff'} =~ /\w/)                         {print MF "$volcanosettings->{'VolcanoNameOnOff'}";}
    else {print MF "On";}
    
    print MF "\nVolcanoNameColor=";
    if ($volcanosettings->{'VolcanoNameColor'} =~ /\w/)                         {print MF "$volcanosettings->{'VolcanoNameColor'}";}
    else {print MF "Brown";}
    
    print MF "\nVolcanoNameAlign=";
    if ($volcanosettings->{'VolcanoNameAlign'} =~ /\w/)                         {print MF "$volcanosettings->{'VolcanoNameAlign'}";}
    else {print MF "Below";}
    
    print MF "\nVolcanoImageList=";
    if ($volcanosettings->{'VolcanoImageList'} =~ /\w/)                         {print MF "$volcanosettings->{'VolcanoImageList'}";}
    else {print MF "";}
    
    print MF "\nVolcanoImageTransparent=";
    if ($volcanosettings->{'VolcanoImageTransparent'} =~ /\w/)                  {print MF "$volcanosettings->{'VolcanoImageTransparent'}";}
    else {print MF "";}
    
    print MF "\nVolcanoDetailList=";
    if ($volcanosettings->{'VolcanoDetailList'} =~ /\w/)                        {print MF "$volcanosettings->{'VolcanoDetailList'}";}
    else {print MF "";}
    
    print MF "\nVolcanoDetailAlign=";
    if ($volcanosettings->{'VolcanoDetailAlign'} =~ /\w/)                       {print MF "$volcanosettings->{'VolcanoDetailAlign'}";}
    else {print MF "";}
    
    print MF "\nVolcanoDetailColor=";
    if ($volcanosettings->{'VolcanoDetailColor'} =~ /\w/)                       {print MF "$volcanosettings->{'VolcanoDetailColor'}";}
    else {print MF "";}

    # STORMS    
    print MF "\n\#\n#STORMS\n\#";
    
    print MF "\nStormColorTrackReal=";
    if ($stormsettings->{'StormColorTrackReal'} =~ /\w/)                        {print MF "$stormsettings->{'StormColorTrackReal'}";}
    else {print MF "Blue";}
    
    print MF "\nStormColorTrackPrediction=";
    if ($stormsettings->{'StormColorTrackPrediction'} =~ /\w/)                  {print MF "$stormsettings->{'StormColorTrackPrediction'}";}
    else {print MF "SkyBlue";}
    
    print MF "\nStormNameOnOff=";
    if ($stormsettings->{'StormNameOnOff'} =~ /\w/)                             {print MF "$stormsettings->{'StormNameOnOff'}";}
    else {print MF "On";}
    
    print MF "\nStormColorName=";
    if ($stormsettings->{'StormColorName'} =~ /\w/)                             {print MF "$stormsettings->{'StormColorName'}";}
    else {print MF "SkyBlue";}
    
    print MF "\nStormAlignName=";
    if ($stormsettings->{'StormAlignName'} =~ /\w/)                             {print MF "$stormsettings->{'StormAlignName'}";}
    else {print MF "Above";}
    
    print MF "\nStormAlignDetail=";
    if ($stormsettings->{'StormAlignDetail'} =~ /\w/)                           {print MF "$stormsettings->{'StormAlignDetail'}";}
    else {print MF "Below";}
    
    print MF "\nStormDetailList=";
    if ($stormsettings->{'StormDetailList'} =~ /\w/)                            {print MF "$stormsettings->{'StormDetailList'}";}
    else {print MF "<type>";}
    
    print MF "\nStormColorDetail=";
    if ($stormsettings->{'StormColorDetail'} =~ /\w/)                           {print MF "$stormsettings->{'StormColorDetail'}";}
    else {print MF "SkyBlue";}
    
    print MF "\nStormImageList=";
    if ($stormsettings->{'StormImageList'} =~ /\w/)                             {print MF "$stormsettings->{'StormImageList'}";}
    else {print MF "";}
    
    print MF "\nStormImageTransparent=";
    if ($stormsettings->{'StormImageTransparent'} =~ /\w/)                      {print MF "$stormsettings->{'StormImageTransparent'}";}
    else {print MF "";}
    
    print MF "\nStormTrackOnOff=";
    if ($stormsettings->{'StormTrackOnOff'} =~ /\w/)                            {print MF "$stormsettings->{'StormTrackOnOff'}";}
    else {print MF "On";}
    
    # ECLIPSE
    print MF "\n\#\n\#ECLIPSE\n\#";
    
    print MF "\nEclipseOnOff=";
    if ($settings->{'EclipseOnOff'} =~ /\w/)                                    {print MF "$settings->{'EclipseOnOff'}";}
    else {print MF "On";}
    
    print MF "\nEclipseNotifyOnOff=";
    if ($settings->{'EclipseNotifyOnOff'} =~ /\w/)                              {print MF "$settings->{'EclipseNotifyOnOff'}";}
    else {print MF "On";}
    
    print MF "\nEclipseNotifyTimeHours=";
    if ($settings->{'EclipseNotifyTimeHours'} =~ /\w/)                          {print MF "$settings->{'EclipseNotifyTimeHours'}";}
    else {print MF "48";}
    
    # NORAD
    print MF "\n\#\n\#NORAD\n\#";
    
    print MF "\nNoradIssImage=";
    if ($noradsettings->{'NoradIssImage'} =~ /\w/)                              {print MF "$noradsettings->{'NoradIssImage'}";}
    else {print MF "iss.png";}
    
    print MF "\nNoradIssText=";
    if ($noradsettings->{'NoradIssText'} =~ /\w/)                               {print MF "$noradsettings->{'NoradIssText'}";}
    else {print MF "";}
    
    print MF "\nNoradIssDetail=";
    if ($noradsettings->{'NoradIssDetail'} =~ /\w/)                             {print MF "$noradsettings->{'NoradIssDetail'}";}
    else {print MF "transparent={0,0,0} trail={orbit,-5,0,5} color=yellow altcirc=0 trail={orbit,-10,0,5}";}
    
    print MF "\nNoradIssOnOff=";
    if ($noradsettings->{'NoradIssOnOff'} =~ /\w/)                              {print MF "$noradsettings->{'NoradIssOnOff'}";}
    else {print MF "On";}
    
    print MF "\nNoradHstImage=";
    if ($noradsettings->{'NoradHstImage'} =~ /\w/)                              {print MF "$noradsettings->{'NoradHstImage'}";}
    else {print MF "hst.png";}
    
    print MF "\nNoradHstText=";
    if ($noradsettings->{'NoradHstText'} =~ /\w/)                               {print MF "$noradsettings->{'NoradHstText'}";}
    else {print MF "";}
    
    print MF "\nNoradHstDetail=";
    if ($noradsettings->{'NoradHstDetail'} =~ /\w/)                             {print MF "$noradsettings->{'NoradHstDetail'}";}
    else {print MF "transparent={0,0,0}";}
    
    print MF "\nNoradHstOnOff=";
    if ($noradsettings->{'NoradHstOnOff'} =~ /\w/)                              {print MF "$noradsettings->{'NoradHstOnOff'}";}
    else {print MF "On";}

    print MF "\nNoradSoyuzImage=";
    if ($noradsettings->{'NoradSoyuzImage'} =~ /\w/)                            {print MF "$noradsettings->{'NoradSoyuzImage'}";}
    else {print MF "soyuz.png";}
    
    print MF "\nNoradSoyuzText=";
    if ($noradsettings->{'NoradSoyuzText'} =~ /\w/)                             {print MF "$noradsettings->{'NoradSoyuzText'}";}
    else {print MF "";}
    
    print MF "\nNoradSoyuzDetail=";
    if ($noradsettings->{'NoradSoyuzDetail'} =~ /\w/)                           {print MF "$noradsettings->{'NoradSoyuzDetail'}";}
    else {print MF "transparent={0,0,0}";}
    
    print MF "\nNoradSoyuzOnOff=";
    if ($noradsettings->{'NoradSoyuzOnOff'} =~ /\w/)                            {print MF "$noradsettings->{'NoradSoyuzOnOff'}";}
    else {print MF "On";}
    
    print MF "\nNoradStsImage=";
    if ($noradsettings->{'NoradStsImage'} =~ /\w/)                              {print MF "$noradsettings->{'NoradStsImage'}";}
    else {print MF "sts.png";}
    
    print MF "\nNoradStsText=";
    if ($noradsettings->{'NoradStsText'} =~ /\w/)                               {print MF "$noradsettings->{'NoradStsText'}";}
    else {print MF "";}
    
    print MF "\nNoradStsDetail=";
    if ($noradsettings->{'NoradStsDetail'} =~ /\w/)                             {print MF "$noradsettings->{'NoradStsDetail'}";}
    else {print MF "transparent={0,0,0}";}
    
    print MF "\nNoradStsOnOff=";
    if ($noradsettings->{'NoradStsOnOff'} =~ /\w/)                              {print MF "$noradsettings->{'NoradStsOnOff'}";}
    else {print MF "On";}
    
    print MF "\nNoradSatImage=";
    if ($noradsettings->{'NoradSatImage'} =~ /\w/)                              {print MF "$noradsettings->{'NoradSatImage'}";}
    else {print MF "sts.png";}
    
    print MF "\nNoradSatText=";
    if ($noradsettings->{'NoradSatText'} =~ /\w/)                               {print MF "$noradsettings->{'NoradSatText'}";}
    else {print MF "";}
    
    print MF "\nNoradSatDetail=";
    if ($noradsettings->{'NoradSatDetail'} =~ /\w/)                             {print MF "$noradsettings->{'NoradSatDetail'}";}
    else {print MF "transparent={0,0,0}";}
    
    print MF "\nNoradSatOnOff=";
    if ($noradsettings->{'NoradSatOnOff'} =~ /\w/)                              {print MF "$noradsettings->{'NoradSatOnOff'}";}
    else {print MF "On";}
    
    print MF "\nNoradMiscOnOff=";
    if ($noradsettings->{'NoradMiscOnOff'} =~ /\w/)                             {print MF "$noradsettings->{'NoradMiscOnOff'}";}
    else {print MF "Off";}
    
    print MF "\nNoradTleNumbers=";
    if ($noradsettings->{'NoradTleNumbers'} =~ /\w/)                            {print MF "$noradsettings->{'NoradTleNumbers'}";}
    else {print MF "";}
    
    print MF "\nNoradMiscDetail=";
    if ($noradsettings->{'NoradMiscDetail'} =~ /\w/)                            {print MF "$noradsettings->{'NoradMiscDetail'}";}
    else {print MF "";}
    
    print MF "\nNoradFileName=";
    if ($noradsettings->{'NoradFileName'} =~ /\w/)                              {print MF "$noradsettings->{'NoradFileName'}";}
    else {print MF "tm";}
    
    # LABEL
    print MF "\n\#\n\#LABELUPDATE\n\#";
    
    print MF "\nLabelOnOff=";
    if ($labelsettings->{'LabelOnOff'} =~ /\w/)                                 {print MF "$labelsettings->{'LabelOnOff'}";}
    else {print MF "On";}
    
    print MF "\nLabelWarningQuake=";
    if ($labelsettings->{'LabelWarningQuake'} =~ /\w/)                          {print MF "$labelsettings->{'LabelWarningQuake'}";}
    else {print MF "84600";}
    
    print MF "\nLabelWarningVolcano=";
    if ($labelsettings->{'LabelWarningVolcano'} =~ /\w/)                        {print MF "$labelsettings->{'LabelWarningVolcano'}";}
    else {print MF "604800";}
    
    print MF "\nLabelWarningStorm=";
    if ($labelsettings->{'LabelWarningStorm'} =~ /\w/)                          {print MF "$labelsettings->{'LabelWarningStorm'}";}
    else {print MF "84600";}
    
    print MF "\nLabelWarningNorad=";
    if ($labelsettings->{'LabelWarningNorad'} =~ /\w/)                          {print MF "$labelsettings->{'LabelWarningNorad'}";}
    else {print MF "604800";}
    
    print MF "\nLabelWarningCloud=";
    if ($labelsettings->{'LabelWarningCloud'} =~ /\w/)                          {print MF "$labelsettings->{'LabelWarningCloud'}";}
    else {print MF "21600";}
    
    print MF "\nLabelColorOk=";
    if ($labelsettings->{'LabelColorOk'} =~ /\w/)                               {print MF "$labelsettings->{'LabelColorOk'}";}
    else {print MF "Green";}
    
    print MF "\nLabelColorWarn=";
    if ($labelsettings->{'LabelColorWarn'} =~ /\w/)                             {print MF "$labelsettings->{'LabelColorWarn'}";}
    else {print MF "Yellow";}
    
    print MF "\nLabelColorError=";
    if ($labelsettings->{'LabelColorError'} =~ /\w/)                            {print MF "$labelsettings->{'LabelColorError'}";}
    else {print MF "Red";}	
    
    # CLOUDS
    print MF "\n\#\n\#CLOUDS\n\#";
    
    print MF "\nCloudRemoteImageName=";
    if ($cloudsettings->{'CloudRemoteImageName'} =~ /\w/)                       {print MF "$cloudsettings->{'CloudRemoteImageName'}";}
    else {print MF "clouds_2048.jpg";}
    
    print MF "\nCloudLocalImageName=";
    if ($cloudsettings->{'CloudLocalImageName'} =~ /\w/)                        {print MF "$cloudsettings->{'CloudLocalImageName'}";}
    else {print MF "clouds_2048.jpg";}
    
    print MF "\nUseFreeCloudImage=";
    if ($cloudsettings->{'UseFreeCloudImage'} =~ /\w/)                          {print MF "$cloudsettings->{'UseFreeCloudImage'}";}
    else {print MF "Yes";}
    
    print MF "\nSubcribedToXplanetClouds=";
    if ($cloudsettings->{'SubcribedToXplanetClouds'} =~ /\w/)                   {print MF "$cloudsettings->{'SubcribedToXplanetClouds'}";}
    else {print MF "No";}
    
    print MF "\nUsername=";
    if ($cloudsettings->{'Username'} =~ /\w/)                                   {print MF "$cloudsettings->{'Username'}";}
    else {print MF "";}
    
    print MF "\nPassword=";
    if ($cloudsettings->{'Password'} =~ /\w/)                                   {print MF "$cloudsettings->{'Password'}";}
    else {print MF "";}
    
    print MF "\nDirectDownload=";
    if ($cloudsettings->{'DirectDownload'} =~ /\w/)                             {print MF "$cloudsettings->{'DirectDownload'}";}
    else {print MF "";}
    
    # MISC	
    print MF "\n\#\n\#MISC\n\#";
    
    print MF "\nEasterEggSurprises=";
    if (settings->{'EasterEggSurprises'} =~ /\w/)                               {print MF "settings->{'EasterEggSurprises'}";}
    else {print MF "1";}
    
    print MF "\nMiscXplanetVersion1OrBetter=";
    if ($settings->{'XplanetVersion'} =~ /\w/)                                  {print MF "$settings->{'XplanetVersion'}";}
    else {print MF "Yes";}
    
    close MF;
    print "Ini File updated to lastest version.\n";
}

sub WriteoutVolcano($) {
    my ($counter) = @_;
    my $recounter = 0;
    
    if ($counter !~ /FAILED/) {
        my $openfile = Volcano;
        open (MF, ">$volcano_marker_file");
        &file_header($openfile);
        
        while ($recounter < $counter) {
            my $long = $volcanodata[$recounter]->{'long'};
            my $lat = $volcanodata[$recounter]->{'lat'};
            my $name = $volcanodata[$recounter]->{'name'};
            my $elev = $volcanodata[$recounter]->{'elev'};
            
            $lat  = sprintf("% 7.2f",$lat);
            $long = sprintf("% 7.2f",$long);
            print MF "$lat $long \"\" color=$volcanosettings->{'VolcanoCircleColorInner'} symbolsize=$volcanosettings->{'VolcanoCircleSizeInner'}\n$lat $long \"\" color=$volcanosettings->{'VolcanoCircleColorMiddle'} symbolsize=$volcanosettings->{'VolcanoCircleSizeMiddle'}\n";
            
            if ($volcanosettings->{'VolcanoNameOnOff'} =~ /On/) {
                if ($volcanosettings->{'VolcanoImageList'} =~ /\w/) {
                    print MF "$lat $long \"$name\" align=$volcanosettings->{'VolcanoNameAlign'} color=$volcanosettings->{'VolcanoNameColor'} image=$volcanosettings->{'VolcanoImageList'} ";
                    
                    if ($volcanosettings->{'VolcanoImageTransparent'} =~ /\d/) {
                        print MF "transparent=$volcanosettings->{'VolcanoImageTransparent'}";
                    }
                }
                else {
                    print MF "$lat $long \"$name\" color=$volcanosettings->{'VolcanoCircleColorOuter'} symbolsize=$volcanosettings->{'VolcanoCircleSizeOuter'} align=$volcanosettings->{'VolcanoNameAlign'}";
                }
            }
            else {
                print MF "$lat $long \"\" color=$volcanosettings->{'VolcanoCircleColorOuter'} symbolsize=$volcanosettings->{'VolcanoCircleSizeOuter'}";
            }
            print MF "\n";
            
            if ($volcanosettings->{'VolcanoDetailList'} =~ /\w/) {
                my $tmp1 = $volcanosettings->{'VolcanoDetailList'};
                
                $tmp1 =~ s/<lat>/$lat/g;
                $tmp1 =~ s/<long>/$long/g;
                $tmp1 =~ s/<elevation>/$elev/g;
                $tmp1 =~ s/<elev>/$elev/g;
                $tmp1 =~ s/<name>/$name/g;
                $tmp1 =~ s/<location>/$locations/g;
                print MF "$lat $long \"$tmp1\" color=$volcanosettings->{'VolcanoDetailColor'} align=$volcanosettings->{'VolcanoDetailAlign'} image=none\n";
            }
            
            $recounter++;
        }
        
        close MF;
    }
}

# elsif ($setting =~ /VolcanoDetailList/) {$volcanosettings->{'VolcanoDetailList'} = $result;}
# elsif ($setting =~ /VolcanoDetailAlign/) {$volcanosettings->{'VolcanoDetailAlign'} = $result;}

sub get_volcanodata() {
    my $flag = 1;
    my $MaxDownloadFrequencyHours = 24;
    my $MaxRetries = 3;
    my $volcanodata_file = "$volcano_marker_file";
    #print "$cloud_image_file\n";
    
    # Get file details
    if (-f $volcanodata_file) {
        my @Stats = stat($volcanodata_file);
        my $FileAge = (time() - $Stats[9]);
        my $FileSize = $Stats[7];
        
        # Check if file is already up to date
        if ($FileAge < 60 * 60 * $MaxDownloadFrequencyHours) {
            print "Volcano data is up to date!\n";
            $flag = 0;
        }
    }
    
    if ($flag != 0) {
        $flag = volcanodata_checked();
    }
    else {
        $flag = "what";
    }
    #print " flag = $flag";
    
    return $flag;
}

sub volcanodata_checked() {
    my $volcanotxt;
    my $counter = 0;
    
    $volcanotxt = get_webpage($volcano_location);
    
    if ($volcanotxt !~ /FAILED/) {
        $volcanotxt =~ s/[\r\n]+//g;
        
        foreach(split("<info>",$volcanotxt)) {
            chomp;
#print $_ ."\n";
#        <category>Geo</category>        <event>Volcano</event>  <responseType>None</responseType>       <urgency>Unknown</urgency>      <severity>Unknown</severity>    <certainty>Observed</certainty> <eventCode><valueName>Volcano Name</valueName><value>Yasur</value></eventCode>  <eventCode><valueName>New Activity</valueName><value>N</value></eventCode>      <eventCode><valueName>Observatory Name (primary)</valueName><value></value></eventCode> <eventCode><valueName>Observatory Link (primary)</valueName><value></value></eventCode> <eventCode><valueName>Observatory Name (secondary)</valueName><value></value></eventCode>       <eventCode><valueName>Observatory Link (secondary)</valueName><value></value></eventCode>       <senderName>Global Volcanism Program (Smithsonian Institution)</senderName>     <headline>Volcanic activity report for Yasur (Vanuatu), 22 May-28 May 2013</headline>   <description>On 28 May, the Vanuatu Geohazards Observatory reported that activity at Yasur continued to increase slightly, and bombs fell around the summit area, the tourist walk, and the parking area. Ash venting and densewhite plumes from the crater were observed. Photos included in the report showed ash emissions and ashfall on 5 and 8 May, and dense white plumes on 23 and 24 May. The Alert Level remained at 2 (on a scale of 0-4).</description>    <web>http://www.volcano.si.edu/weekly_report.cfm</web>  <contact>Source: Vanuatu Geohazards Observatory </contact>      <area><areaDesc>Vanuatu</areaDesc><circle>-19.530,169.442,0</circle></area></info></alert>
#        <category>Geo</category>        <event>Volcano</event>  <responseType>None</responseType>       <urgency>Unknown</urgency>      <severity>Unknown</severity>    <certainty>Observed</certainty> <eventCode><valueName>Volcano Name</valueName><value>Shiveluch</value></eventCode>      <eventCode><valueName>New Activity</valueName><value>No</value></eventCode>     <eventCode><valueName>Observatory Name (primary)</valueName><value>Kamchatka Volcanic Eruption Response Team</value></eventCode>        <eventCode><valueName>Observatory Link (primary)</valueName><value>http://www.kscnet.ru/ivs/kvert/index_eng.php</value></eventCode><eventCode><valueName>Observatory Name (secondary)</valueName><value>Institute of Volcanology and Seismology</value></eventCode>        <eventCode><valueName>Observatory Link (secondary)</valueName><value>http://www.kscnet.ru/ivs/volcanoes/holocene/index.htm</value></eventCode>  <senderName>Global Volcanism Program (Smithsonian Institution)</senderName>     <headline>Volcanic activity report for Shiveluch (Russia), 2 April-8 April 2014</headline>      <description>KVERT reported that during 28 March-4 April lava-dome extrusion at Shiveluch was accompanied by ash explosions, incandescence, hot avalanches, and fumarolic activity. A bright thermal anomaly was detected daily in satellite images. The Aviation ColorCode remained at Orange. </description> <web>http://www.volcano.si.edu/weekly_report.cfm</web>  <contact>Source: Kamchatkan Volcanic Eruption Response Team (KVERT)</contact>   <area><areaDesc>Russia</areaDesc><circle>56.653,161.360 0</circle></area></info>
#if ( /.*\<valueName\>Volcano Name\<\/valueName\>\<value\>([A-Z,\s]+)\<\/value\>.*\<areaDesc\>([A-Z,\-,\s]+)\<\/areaDesc\>\<circle\>([\d\-\.]+),([\d\-\.]+).[\d\-\.]+\<\/circle\>.*/i) {
#print "name = $1\n";
#print "area = $2\n";
#print "lat = $3\n";
#print "long = $4\n\n";
#}
            
            if ( /.*\<valueName\>Volcano Name\<\/valueName\>\<value\>([A-Z,\s]+)\<\/value\>.*\<areaDesc\>([A-Z,\-,\s]+)\<\/areaDesc\>\<circle\>([\d\-\.]+),([\d\-\.]+).[\d\-\.]+\<\/circle\>.*/i) {
                my ($name,$area,$lat,$long)=($1,$2,$3,$4);
                
                $elev = "UNKNOWN";
                #print "Name = $name\nLocation = $location\nDetail = $detail\nElev = $elev\n\n";
                
                if ($detail =~ /(\d+\.\d+)&deg;([NS])/) {
                    my $sign;
                    
                    ($lat,$sign)=($1,$2);
                    if ($sign =~ /s/i) {
                        $lat *= -1;
                    }
                    else {
                        $lat *= 1;
                    }
                }
                
                if ($detail =~ /(\d+\.\d+)&deg;([EW])/) {
                    my $sign;
                    
                    ($long,$sign)=($1,$2);
                    if ($sign =~ /w/i) {
                        $long *= -1;
                    }
                    else {
                        $long *= 1;
                    }
                }
   #Degree sign     Numeric Referance&#176;  °  &deg;  MAC=161  WINTEL=176 UNICODE U+00B0  °
                if ($detail =~ /(\d+\.\d+)\x{00B0}([NS])/) {
                    my $sign;
                     
                    ($lat,$sign)=($1,$2);
                    if ($sign =~ /s/i) {
                        $lat *= -1;
                    }
                    else {
                        $lat *= 1;
                    }
                }
                
                if ($detail =~ /(\d+\.\d+)&#176([NS])/) {
                    my $sign;
                    
                    ($lat,$sign)=($1,$2);
                    if ($sign =~ /s/i) {
                        $lat *= -1;
                    }
                    else {
                        $lat *= 1;
                    }
                }
                
                if ($detail =~ /(\d+\.\d+)\x{00B0}([EW])/) {
                    my $sign;
                    
                    ($long,$sign)=($1,$2);
                    if ($sign =~ /w/i) {
                        $long *= -1;
                    }
                    else {
                        $long *= 1;
                    }
                }
                
                if ($detail =~ /(\d+\.\d+)&#176([EW])/) {
                    my $sign;
                    
                    ($long,$sign)=($1,$2);
                    if ($sign =~ /w/i) {
                        $long *= -1;
                    }
                    else {
                        $long *= 1;
                    }
                }
                
                if ($detail =~ /summit elev\..*?([\d,]+)/) {
                    $elev=$1;
                    $elev =~ s/\D//;
                    $elev *=1;
                }
                
                $name =~ s/\&(.).*?\;/lc($1)/eg;
                $name = lc($name);
                $name =~ s/\b(\w)/uc($1)/eg;
                
                if ($name !~ /Additional/) {
                    
####### FIX ME IF THIS BREAKS STUFF
# print "lat=$lat. long=$long.\n";
# print "name=$name.\n";
# print "location=$area.\n";
# print "elev=$elev.\n";
# print "$detail.\n";
################################

                    push @volcanodata, {
                        'lat'    => $lat,
                        'long'   => $long,
                        'name'   => $name,
                        'elev'   => $elev,
                        'location'   => $area,
                    };
                    
                    $counter++;
                }
            }
        }
        
        print "  Updated volcano information\n";
        return $counter;
    }
    else {
        print "  WARNING... unable to access or download updated volcano information\n";
        return $volcanotxt;
    }
}

sub get_noraddata() {
    my $flag = 1;
    my $MaxDownloadFrequencyHours = 12;
    my $MaxRetries = 3;
    my $tlefile = "$isstle_file";
    #print "$cloud_image_file\n";
    
    # Get file details
    if (-f $tlefile)	{
        my @Stats = stat($tlefile);
        my $FileAge = (time() - $Stats[9]);
        my $FileSize = $Stats[7];
        
        
        # Check if file is already up to date
        if ($FileAge < 60 * 60 * $MaxDownloadFrequencyHours) {
            print "TLEs are up to date!\n";
            $flag = 3;
        }
    }
    
    if ($flag != 3) {
        $flag = norad_checked();
    }
    else {
        $flag = "what";
    }
    
    return $flag;
}

sub norad_checked() {
    if ($noradsettings->{'NoradFileName'} =~ /\w+/) {
        $isstle_file = "$xplanet_satellites_dir/$noradsettings->{'NoradFileName'}.tle";
        $iss_file = "$xplanet_satellites_dir/$noradsettings->{'NoradFileName'}";
    }
    #print "Using files:$iss_file,\n            $isstle_file\n";
    
    my $counter = 0;
    my $isstxt=get_webpage($iss_location);
    my $hsttxt=get_webpage($hst_location);
    my $ststxt=get_webpage($sts_location);
    my $otherlocations1txt=get_webpage($other_locations1);
    
    if ($isstxt eq FAILED ) {
        return "FAILED";
    }
    else {
        my $openfile = "Satelitte TLE File";
        open(MF, ">$isstle_file");
        #&file_header($openfile);
        foreach(split("\n",$isstxt)) {
            print MF "$_\n";
        }
        foreach(split("\n",$hsttxt)) {
            print MF "$_\n";
        }
        foreach(split("\n",$otherlocations1txt)) {
            print MF "$_\n";
        }
        
        if ($ststxt !~ /</) {
            foreach(split("\n",$ststxt)) {
                print MF "$_\n";
            }
        }
        close(MF);
        
        my $stsyes = 0;
        my $soyuzyes= 0;
        my $TLEline = 0;
        my $openfile = "Satellite Track";
        
        open(MF, ">$iss_file");
        &file_header($openfile);
        
        if ($ststxt !~ /</) {
            foreach(split("\n",$ststxt)) {
                ($v1, $v2, $v3, $v4, $v5, $v6, $v7, $v8, $v9) = split;
                
                if ($TLEline eq 3) {$TLEline = 0;}
                
                if ($TLEline eq 0) {
                    if ($v1 =~ /STS/) {$stsyes = 1;}
                    elsif ($v1 =~ /HST/) {$unknown = 0;}
                    elsif ($v1 =~ /ISS/) {$unknown = 0;}
                    elsif ($v1 =~ /SOYUZ/) {$soyuzyes = 1;}
                    else {$unknown = 1;}
                }
                #print "Unknown = $unknown stsyes = $stsyes soyuz = $soyuzyes\n";
                
                if ($stsyes eq 1) {
                    if ($stsyes eq 1 && $TLEline eq 2) {
                        my $file = $xplanet_images_dir.'/'.$noradsettings->{'NoradStsImage'};
                        -e $file || &update_file(STS);
                        
                        if ($noradsettings->{'NoradStsOnOff'} =~ /On/) {
                            print MF "$v2 \"$noradsettings->{'NoradStsText'}\" image=$noradsettings->{'NoradStsImage'} $noradsettings->{'NoradStsDetail'}\n";
                        }
                        $stsyes = 0;
                    }
                }
                elsif ($unknown eq 1) {
                    if ($unknown eq 1 && $TLEline eq 2) {
                        my $file = $xplanet_images_dir.'/'.$noradsettings->{'NoradSatImage'};
                        -e $file || &update_file(SAT);
                        
                        if ($noradsettings->{'NoradSatOnOff'} =~ /On/) {
                            print MF "$v2 \"$noradsettings->{'NoradSatText'}\" image=$noradsettings->{'NoradSatImage'} $noradsettings->{'NoradSatDetail'}\n";
                        }
                        $unknown = 0;
                    }
                }
                
                $TLEline ++;
            }
        }
        
        if ($isstxt !~ /</) {
            foreach(split("\n",$isstxt)) {
                ($v1, $v2, $v3, $v4, $v5, $v6, $v7, $v8, $v9) = split;
                
                if ($TLEline eq 3) {$TLEline = 0;}
                if ($TLEline eq 0) {
                    if ($v1 =~ /SOYUZ/) {$soyuzyes = 1;}
                }
                if ($soyuzyes eq 1) {
                    if ($soyuzyes eq 1 && $TLEline eq 2) {
                        my $file = $xplanet_images_dir.'/'.$noradsettings->{'NoradSoyuzImage'};
                        -e $file || &update_file(SOYUZ);
                        if ($noradsettings->{'NoradSoyuzOnOff'} =~ /On/) {
                            print MF "$v2 \"$noradsettings->{'NoradSoyuzText'}\" image=$noradsettings->{'NoradSoyuzImage'} $noradsettings->{'NoradSoyuzDetail'}\n";
                        }
                        
                        $soyuzyes = 0;
                    }
                }
                
                $TLEline ++;
            }
        }
        
        my $file = $xplanet_images_dir.'/'.$noradsettings->{'NoradIssImage'};
        -e $file || &update_file(ISS);
        if ($noradsettings->{'NoradIssOnOff'} =~ /On/) {
            print MF "25544 \"$noradsettings->{'NoradIssText'}\" image=$noradsettings->{'NoradIssImage'} $noradsettings->{'NoradIssDetail'}\n";
        }
        
        my $file = $xplanet_images_dir.'/'.$noradsettings->{'NoradHstImage'};
        -e $file || &update_file(HST);
        if ($noradsettings->{'NoradHstOnOff'} =~ /On/) {
            print MF "20580 \"$noradsettings->{'NoradHstText'}\" image=$noradsettings->{'NoradHstImage'} $noradsettings->{'NoradHstDetail'}\n";
        }
        
        if ($noradsettings->{'NoradMiscOnOff'} =~ /On/) {
            my ($tmp1,$tmp2,$tmp2,$tmp4,$tmp5) = split " ",$noradsettings->{'NoradTleNumbers'},5;
            
            if ($tmp1 =~ /\d\d\d\d\d/) {
                print MF "$tmp1 \"\" image=$tmp1.gif $noradsettings->{'NoradMiscDetail'}\n";
            }
            
            if ($tmp2 =~ /\d\d\d\d\d/) {
                print MF "$tmp2 \"\" image=$tmp2.gif $noradsettings->{'NoradMiscDetail'}\n";
            }
            
            if ($tmp3 =~ /\d\d\d\d\d/) {
                print MF "$tmp3 \"\" image=$tmp3.gif $noradsettings->{'NoradMiscDetail'}\n";
            }
            
            if ($tmp4 =~ /\d\d\d\d\d/) {
                print MF "$tmp4 \"\" image=$tmp4.gif $noradsettings->{'NoradMiscDetail'}\n";
            }
            
            if ($tmp5 =~ /\d\d\d\d\d/) {
                print MF "$tmp5 \"\" image=$tmp5.gif $noradsettings->{'NoradMiscDetail'}\n";
            }
        }
        close(MF);
        
        return "1";
    }
    
    return "what";
}

sub update_file () {
    my ($type) = @_;
    
    if ($type =~ /ISS/) {
        $noradsettings->{'NoradIssImage'} = "iss.png";
        $file = $xplanet_images_dir.'/'.$noradsettings->{'NoradIssImage'};
        -e $file || &get_file($noradsettings->{'NoradIssImage'});
    }
    
    if ($type =~ /HST/) {
        $noradsettings->{'NoradHstImage'} = "hst.png";
        $file = $xplanet_images_dir.'/'.$noradsettings->{'NoradHstImage'};
        -e $file || &get_file($noradsettings->{'NoradHstImage'});
    }
    
    if ($type =~ /STS/) {
        $noradsettings->{'NoradStsImage'} = "sts.png";
        $file = $xplanet_images_dir.'/'.$noradsettings->{'NoradStsImage'};
        -e $file || &get_file($noradsettings->{'NoradStsImage'});
    }
    
    if ($type =~ /SAT/) {
        $noradsettings->{'NoradSatImage'} = "sat.png";
        $file = $xplanet_images_dir.'/'.$noradsettings->{'NoradSatImage'};
        -e $file || &get_file($noradsettings->{'NoradSatImage'});
    }
    
    if ($type =~ /SOYUZ/) {
        $noradsettings->{'NoradSoyuzImage'} = "soyuz.png";
        $file = $xplanet_images_dir.'/'.$noradsettings->{'NoradSoyuzImage'};
        -e $file || &get_file($noradsettings->{'NoradSoyuzImage'});
    }
}

sub WriteoutLabel () {
    my ($update_earth,$update_norad,$update_cloud,$update_hurricane,$update_volcano,$update_label) = @_;
    
    if ($update_earth >= 1) {$update_earth = 1;}
    if ($update_norad >= 1) {$update_norad = 1;}
    if ($update_cloud >= 1) {$update_cloud = 1;}
    if ($update_hurricane >= 1) {$update_hurricane = 1;}
    if ($update_hurricane == -1) {$update_hurricane = 1;}
    if ($update_volcano >= 1) {$update_volcano = 1;}
    if ($update_label >= 1) {
        $update_earth = 0;
        $update_norad = 0;
        $update_cloud = 0;
        $update_hurricane = 0;
        $update_volcano = 0;
    }
    
    my $counter = 0;
    my $ok_color = $labelsettings->{'LabelColorOk'};
    my $warn_color = $labelsettings->{'LabelColorWarn'};
    my $failed_color = $labelsettings->{'LabelColorError'};
    
    open(MF, "<$label_file");
    while (<MF>) {
        ($Yco_ords[$counter], $Xco_ords[$counter], $text1[$counter], $text2[$counter], $text3[$counter], $text4[$counter], $weekday[$counter], $monthday[$counter], $monthlet[$counter], $yeartime[$counter], $colour[$counter], $image[$counter], $position[$counter]) = split (" ");
        $counter ++;
    }
    close (MF);
    
    my @warning_lenght;
    push @warning_lenght, {
        'quake'             => ($labelsettings->{'LabelWarningQuake'} *1),
        'cloud'             => ($labelsettings->{'LabelWarningCloud'} *1),
        'norad'             => ($labelsettings->{'LabelWarningNorad'} *1),
        'hurricane'         => ($labelsettings->{'LabelWarningStorm'} *1),
        'volcano'           => ($labelsettings->{'LabelWarningVolcano'} *1),
        'quakeerror'        => ($labelsettings->{'LabelWarningQuake'} *2),
        'clouderror'        => ($labelsettings->{'LabelWarningCloud'} *2),
        'noraderror'        => ($labelsettings->{'LabelWarningNorad'} *2),
        'hurricaneerror'    => ($labelsettings->{'LabelWarningStorm'} *2),
        'volcanoerror'      => ($labelsettings->{'LabelWarningVolcano'} *2),
    };
    
    ($sec,$min,$hour,$mday,$mon,$year,$wday,$yday,$isdst) = localtime(time);
    $thisday = (Sun,Mon,Tues,Wed,Thurs,Fri,Sat)[(localtime)[6]];
    $thismonth = (Jan,Feb,March,April,May,June,July,Aug,Sept,Oct,Nov,Dec)[(localtime)[4]];
    $year += 1900;
    $time_now = time;
    
    open(MF, ">$label_file");
    $openfile = UpdateLabel;
    &file_header($openfile);
    
    $recounter = 0;
    $position = 0;

    while ($recounter != $counter) {
        if ($update_earth ne 0 && $text1[$recounter] =~ /Earthquake/) {
            print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] \"Earthquake Infomation Last Updated";
            $position++;
            substr($yeartime[$recounter],-1,1) = "";
            
            if ($update_earth eq FAILED && $colour[$recounter] =~ $ok_color) {
                print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$warn_color";
            }
            elsif ($update_earth eq FAILED && $colour[$recounter] =~ $warn_color) {
                my $monnum = num_of_month($monthlet[$recounter]);
                chomp $yeartime[$recounter];
                my ($year,$min,$sec) = split(":",$yeartime[$recounter],3);
                my ($year,$hour) = split(",",$year,2);
                $year = ($year - 1900);
                my $time_state = timelocal($sec,$min,$hour,$monthday[$recounter],$monnum,$year);
                my $time_difference = $time_now-$time_state;
                
                if ($time_difference < $warning_lenght[0]->{'quake'}) {
                    print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$warn_color";
                }
                else {
                    print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$failed_color";
                }
            }
            elsif ($update_earth eq FAILED) {
                print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$failed_color";
            }
            else {
                printf MF " $thisday $mday $thismonth $year,%02d:%02d:%02d\" color=$ok_color", $hour,$min,$sec;
            }
            print MF " image=none position=pixel\n";
            
            $update_earth = 0;
        }
        elsif ($update_norad ne 0 && $text1[$recounter] =~ /NORAD/) {
            print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] \"NORAD Infomation Last Updated";
            $position++;
            substr($yeartime[$recounter],-1,1) = "";
            
            if ($update_norad eq FAILED && $colour[$recounter] =~ $ok_color) {
                print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$warn_color";
            }
            elsif ($update_norad eq FAILED && $colour[$recounter] =~ $warn_color) {
                my $mon = num_of_month($monthlet[$recounter]);
                chomp $yeartime[$recounter];
                my ($year,$min,$sec) = split(":",$yeartime[$recounter],3);
                my ($year,$hour) = split(",",$year,2);
                my $year = ($year - 1900);
                my $time_state = timelocal($sec,$min,$hour,$monthday[$recounter],$mon,$year);
                my $time_difference = $time_now-$time_state;
                
                if ($time_difference < $warning_lenght[0]->{'norad'}) {
                    print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$warn_color";
                }
                else {
                    print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$failed_color";
                }
            }
            elsif ($update_norad eq FAILED) {
                print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$failed_color";
            }
            else {
                printf MF " $thisday $mday $thismonth $year,%02d:%02d:%02d\" color=$ok_color", $hour, $min, $sec;
            }
            print MF " image=none position=pixel\n";
            
            $update_norad = 0;
        }
        elsif ($update_cloud ne 0 && $text1[$recounter] =~ /Cloud/) {
            print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] \"Cloud Map Last Updated";
            $position++;
            substr($yeartime[$recounter],-1,1) = "";
            
            if ($update_cloud eq FAILED && $colour[$recounter] =~ $ok_color) {
                print MF "$weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$warn_color";
            }
            elsif ($update_cloud eq FAILED && $colour[$recounter] =~ $warn_color) {
                my $mon = num_of_month($monthlet[$recounter]);
                chomp $yeartime[$recounter];
                my ($year,$min,$sec) = split(":",$yeartime[$recounter],3);
                my ($year,$hour) = split(",",$year,2);
                my $year = ($year - 1900);
                my $time_state = timelocal($sec,$min,$hour,$monthday[$recounter],$mon,$year);
                my $time_difference = $time_now-$time_state;
                
                if ($time_difference < $warning_lenght[0]->{'cloud'}) {
                    print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$warn_color";
                }
                else {
                    print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$failed_color";
                }
            }
            elsif ($update_cloud eq FAILED) {
                print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$failed_color";
            }
            else {
                printf MF " $thisday $mday $thismonth $year,%02d:%02d:%02d\" color=$ok_color", $hour, $min, $sec;
            }
            print MF " image=none position=pixel\n";
            
            $update_cloud = 0;
        }
        elsif ($update_hurricane ne 0 && $text1[$recounter] =~ /Storm/) {
            print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] \"Storm Infomation Last Updated";
            $position++;
            substr($yeartime[$recounter],-1,1) = "";
            
            if ($update_hurricane eq FAILED && $colour[$recounter] =~ $ok_color) {
                print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$warn_color";
            }
            elsif ($update_hurricane eq FAILED && $colour[$recounter] =~ $warn_color) {
                my $mon = num_of_month($monthlet[$recounter]);
                chomp $yeartime[$recounter];
                my ($year,$min,$sec) = split(":",$yeartime[$recounter],3);
                my ($year,$hour) = split(",",$year,2);
                my $year = ($year - 1900);
                my $time_state = timelocal($sec,$min,$hour,$monthday[$recounter],$mon,$year);
                my $time_difference = $time_now-$time_state;
                if ($time_difference < $warning_lenght[0]->{'hurricane'}) {
                    print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$warn_color";
                }
                else {
                    print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$failed_color";
                }
            }
            elsif ($update_hurricane eq FAILED) {
                print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$failed_color";
            }
            else {
                printf MF " $thisday $mday $thismonth $year,%02d:%02d:%02d\" color=$ok_color", $hour, $min, $sec;
            }
            print MF " image=none position=pixel\n";
            
            $update_hurricane = 0;
        }
        elsif ($update_volcano ne 0 && $text1[$recounter] =~ /Volcano/) {
            print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] \"Volcano Infomation Last Updated";
            $position++;
            substr($yeartime[$recounter],-1,1) = "";
            
            if ($update_volcano eq FAILED && $colour[$recounter] =~ $ok_color) {
                print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$warn_color";
            }
            elsif ($update_volcano eq FAILED && $colour[$recounter] =~ $warn_color) {
                my $mon = num_of_month($monthlet[$recounter]);
                chomp $yeartime[$recounter];
                my ($year,$min,$sec) = split(":",$yeartime[$recounter],3);
                my ($year,$hour) = split(",",$year,2);
                my $year = ($year - 1900);
                my $time_state = timelocal($sec,$min,$hour,$monthday[$recounter],$mon,$year);
                my $time_difference = $time_now-$time_state;
                
                if ($time_difference < $warning_lenght[0]->{'volcano'}) {
                    print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$warn_color";
                }
                else {
                    print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$failed_color";
                }
            }
            elsif ($update_volcano eq FAILED) {
                print MF " $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter]\" color=$failed_color";
            }
            else {
                printf MF " $thisday $mday $thismonth $year,%02d:%02d:%02d\" color=$ok_color", $hour, $min, $sec;
            }
            print MF " image=none position=pixel\n";
            
            $update_volcano = 0;
        }
        elsif ($Yco_ords[$recounter] =~ /-\d\d/ && $text3[$recounter] =~ /Last/ && $text4[$recounter] =~ /Updated/) {
            if ($text1[$recounter] =~ /Cloud/) {
                my $mon = num_of_month($monthlet[$recounter]);
                chomp $yeartime[$recounter];
                my ($year,$min,$sec) = split(":",$yeartime[$recounter],3);
                my ($year,$hour) = split(",",$year,2);
                my $year = ($year - 1900);
                my $time_state = timelocal($sec,$min,$hour,$monthday[$recounter],$mon,$year);
                my $time_difference = $time_now-$time_state;
                
                if ($time_difference > $warning_lenght[0]->{'clouderror'}) {
                    print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] color=$failed_color $image[$recounter] $position[$recounter]\n";
                }
                elsif ($time_difference > $warning_lenght[0]->{'cloud'}) {
                    print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] color=$warn_color $image[$recounter] $position[$recounter]\n";
                }
                else {
                    print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] $colour[$recounter] $image[$recounter] $position[$recounter]\n";
                }
            }
            elsif ($text1[$recounter] =~ /NORAD/) {
                my $mon = num_of_month($monthlet[$recounter]);
                chomp $yeartime[$recounter];
                my ($year,$min,$sec) = split(":",$yeartime[$recounter],3);
                my ($year,$hour) = split(",",$year,2);
                my $year = ($year - 1900);
                my $time_state = timelocal($sec,$min,$hour,$monthday[$recounter],$mon,$year);
                my $time_difference = $time_now-$time_state;
                
                if ($time_difference > $warning_lenght[0]->{'noraderror'}) {
                    print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] color=$failed_color $image[$recounter] $position[$recounter]\n";
                }
                elsif ($time_difference > $warning_lenght[0]->{'norad'}) {
                    print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] color=$warn_color $image[$recounter] $position[$recounter]\n";
                }
                else {
                    print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] $colour[$recounter] $image[$recounter] $position[$recounter]\n";
                }
            }
            elsif ($text1[$recounter] =~ /Volcano/) {
                my $mon = num_of_month($monthlet[$recounter]);
                chomp $yeartime[$recounter];
                my ($year,$min,$sec) = split(":",$yeartime[$recounter],3);
                my ($year,$hour) = split(",",$year,2);
                my $year = ($year - 1900);
                my $time_state = timelocal($sec,$min,$hour,$monthday[$recounter],$mon,$year);
                my $time_difference = $time_now-$time_state;
                
                if ($time_difference > $warning_lenght[0]->{'volcanoerror'}) {
                    print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] color=$failed_color $image[$recounter] $position[$recounter]\n";
                }
                elsif ($time_difference > $warning_lenght[0]->{'volcano'}) {
                    print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] color=$warn_color $image[$recounter] $position[$recounter]\n";
                }
                else {
                    print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] $colour[$recounter] $image[$recounter] $position[$recounter]\n";
                }
            }
            elsif ($text1[$recounter] =~ /Storm/) {
                my $mon = num_of_month($monthlet[$recounter]);
                chomp $yeartime[$recounter];
                my ($year,$min,$sec) = split(":",$yeartime[$recounter],3);
                my ($year,$hour) = split(",",$year,2);
                my $year = ($year - 1900);
                my $time_state = timelocal($sec,$min,$hour,$monthday[$recounter],$mon,$year);
                my $time_difference = $time_now-$time_state;
                
                if ($time_difference > $warning_lenght[0]->{'hurricaneerror'}) {
                    print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] color=$failed_color $image[$recounter] $position[$recounter]\n";
                }
                elsif ($time_difference > $warning_lenght[0]->{'hurricane'}) {
                    print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] color=$warn_color $image[$recounter] $position[$recounter]\n";
                }
                else {
                    print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] $colour[$recounter] $image[$recounter] $position[$recounter]\n";
                }
            }
            elsif ($text1[$recounter] =~ /Earthquake/) {
                my $mon = num_of_month($monthlet[$recounter]);
                chomp $yeartime[$recounter];
                my ($year,$min,$sec) = split(":",$yeartime[$recounter],3);
                my ($year,$hour) = split(",",$year,2);
                my $year = ($year - 1900);
                my $time_state = timelocal($sec,$min,$hour,$monthday[$recounter],$mon,$year);
                my $time_difference = $time_now-$time_state;
                
                if ($time_difference > $warning_lenght[0]->{'quakeerror'}) {
                    print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] color=$failed_color $image[$recounter] $position[$recounter]\n";
                }
                elsif ($time_difference > $warning_lenght[0]->{'quake'}) {
                    print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] color=$warn_color $image[$recounter] $position[$recounter]\n";
                }
                else {
                    print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] $colour[$recounter] $image[$recounter] $position[$recounter]\n";
                }
            }
            else {
                print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] $colour[$recounter] $image[$recounter] $position[$recounter]\n";
            }
            
            $position++;
        }
        elsif ($text2[$recounter] =~ /santa.png/) {}
        elsif ($Yco_ords[$recounter] !~ /\#/) {
            print MF "$Yco_ords[$recounter] $Xco_ords[$recounter] $text1[$recounter] $text2[$recounter] $text3[$recounter] $text4[$recounter] $weekday[$recounter] $monthday[$recounter] $monthlet[$recounter] $yeartime[$recounter] $colour[$recounter] $image[$recounter] $position[$recounter]\n";
        }
        
        $recounter++;
    }
    
    if ($update_earth eq 1) {
        $labellocate = (($position*15)+53);
        printf MF "-$labellocate -13 \"Earthquake Infomation Last Updated $thisday $mday $thismonth $year,%02d:%02d:%02d\" color=$ok_color image=none position=pixel\n", $hour, $min, $sec;
        $position++;
        $update_earth = 0;
    }
    
    if ($update_norad eq 1) {
        $labellocate = (($position*15)+53);
        printf MF "-$labellocate -13 \"NORAD Infomation Last Updated $thisday $mday $thismonth $year,%02d:%02d:%02d\" color=$ok_color image=none position=pixel\n", $hour, $min, $sec;
        $position++;
        $update_norad = 0;
    }
    
    if ($update_cloud eq 1) {
        $labellocate = (($position*15)+53);
        printf MF "-$labellocate -12 \"Cloud Map Last Updated $thisday $mday $thismonth $year,%02d:%02d:%02d\" color=$ok_color image=none position=pixel\n", $hour, $min, $sec;
        $position++;
        $update_cloud = 0;
    }
    
    if ($update_hurricane eq 1) {
        $labellocate = (($position*15)+53);
        printf MF "-$labellocate -13 \"Storm Infomation Last Updated $thisday $mday $thismonth $year,%02d:%02d:%02d\" color=$ok_color image=none position=pixel\n", $hour, $min, $sec;
        $position++;
        $update_hurricane = 0;
    }
    
    if ($update_volcano eq 1) {
        $labellocate = (($position*15)+53);
        printf MF "-$labellocate -13 \"Volcano Infomation Last Updated $thisday $mday $thismonth $year,%02d:%02d:%02d\" color=$ok_color image=none position=pixel\n", $hour, $min, $sec;
        $position++;
        $update_volcano = 0;
    }
    
    if ($update_earth eq FAILED) {
        $labellocate = (($position*15)+53);
        print MF "-$labellocate -13 \"Earthquake Infomation Last Updated FAILED TO UPDATE DATA\"color=$failed_color image=none position=pixel\n";
        $position++;
        $update_earth = 0;
    }
    
    if ($update_norad eq FAILED) {
        $labellocate = (($position*15)+53);
        print MF "-$labellocate -13 \"NORAD Infomation Last Updated FAILED TO UPDATE DATA\" color=$failed_color image=none position=pixel\n";
        $position++;
        $update_norad = 0;
    }
    
    if ($update_cloud eq FAILED) {
        $labellocate = (($position*15)+53);
        print MF "-$labellocate -12 \"Cloud Map Last Updated FAILED TO UPDATE DATA\" color=$failed_color image=none position=pixel \n";
        $position++;
        $update_cloud = 0;
    }
    
    if ($update_hurricane eq FAILED) {
        $labellocate = (($position*15)+53);
        print MF "-$labellocate -13 \"Storm Infomation Last Updated FAILED TO UPDATE DATA\" color=$failed_color image=none position=pixel\n";
        $position++;
        $update_hurricane = 0;
    }
    
    if ($update_volcano eq FAILED) {
        $labellocate = (($position*15)+53);
        print MF "-$labellocate -13 \"Volcano Infomation Last Updated FAILED TO UPDATE DATA\" color=$failed_color image=none position=pixel\n";
        $position++;
        $update_volcano = 0;
    }
    
    close (MF);
}

sub get_eclipsedata() {
    my $counter = 0;
    my $file  = "SEpath.html";
    my @eclipsedatatmp;
    print "Please Wait Building Eclipse Database.  This could take an minute.\n.";
    my $eclipsetxt  =  get_webpage($eclipse_location.$file);
    if ($eclipsetxt =~ /FAILED/ ) {$eclipseoverride = 1;}
    else {
        open (MF, ">$eclipse_data_file");
        $tsn = localtime(time);
        print MF "#\n# Last Updated: $tsn\n#\n";
        print MF "[DATA]\n";
        
        foreach (split(/<TR>/,$eclipsetxt)) {
            s/^\s+//;
            s/\s+$//;
            s/\s+/ /g;
            s/<TD>/ /g;
            s/<\/A>//g;
            s/<A HREF="//g;
            s/">//g;
            s/path//g;
            s/map//g;
            ($a1,$a2,$a3,$a4,$a5,$a6,$a7,$a8,$a9,$a10) = split " ";
            if ($a1 =~ /\d\d\d\d/) {
                my $year = $a1;
                my $monthtxt = $a2;
                my $monthnum = num_of_month($monthtxt);
                my $dayofmonth = $a3;
                my $type = $a4;
                $type = sprintf("%-7s",$type);
                my $saros = $a6;
                my $eclmag = $a7;
                my $duration = $a8;
                my $path = $a10;
                substr($path, 2, 0) = path;
                my $time_now = time;
                $secsperday = 86400;
                my $time_state = timelocal(59,59,23,$dayofmonth,$monthnum,$year);
                
                
                if ($time_state < $time_now) {}
                else {
                    print ".";
                    print MF "$dayofmonth, $monthtxt, $year, $type, $saros, $eclmag, $duration, CRUDE\n";
                    push @eclipsedatatmp, {'path' => $path,};
                    $counter++;
                }
            }
        }
    }
    
    $recounter = 0;
    
    print "\nBuilt Index $counter Entries, Starting to fill data sets.\n";
    while ($recounter < $counter) {
        $eclipsetxt  =  get_webpage($eclipse_location.$eclipsedatatmp[$recounter]->{'path'});
        
        if ($eclipsetxt =~ /FAILED/) {return $eclipsetxt;}
        else {
            print MF "[TRACK,$recounter]\n";
            my $tmp;
            my $tmp1;
            my $tmp2;
            
            foreach (split(/\d\dm\d\d.\ds/,$eclipsetxt)) {
                s/^\s+//;
                s/\s+$//;
                s/\s+/ /g;
                ($a1,$a2,$a3,$a4,$a5,$a6,$a7,$a8,$a9,$a10,$a11,$a12,$a13,$a14) = split " ";
                
                if ($a1 =~ /\d\d:\d\d/) {
                    my ($hour,$min) = split ":",$a1;
                    my ($tmp,$tmp1) = split '\.',$a3;
                    $tmp2 = substr($tmp1,-1,1);
                    chop $tmp1;
                    
                    if ($tmp1 >= 5) {$tmp++;}
                    my $northlat = $a2.'.'.$tmp.$tmp2;
                    my ($tmp,$tmp1) = split '\.',$a5;
                    $tmp2 = substr($tmp1,-1,1);
                    chop $tmp1;
                    
                    if ($tmp1 >= 5) {$tmp++;}
                    my $northlong = $a4.'.'.$tmp.$tmp2;
                    my ($tmp,$tmp1) = split '\.',$a7;
                    $tmp2 = substr($tmp1,-1,1);
                    chop $tmp1;
                    
                    if ($tmp1 >= 5) {$tmp++;}
                    my $southlat = $a6.'.'.$tmp.$tmp2;
                    my ($tmp,$tmp1) = split '\.',$a9;
                    $tmp2 = substr($tmp1,-1,1);
                    chop $tmp1;
                    
                    if ($tmp1 >= 5) {$tmp++;}
                    my $southlong = $a8.'.'.$tmp.$tmp2;
                    my ($tmp,$tmp1) = split '\.',$a11;
                    $tmp2 = substr($tmp1,-1,1);
                    chop $tmp1;
                    
                    if ($tmp1 >= 5) {$tmp++;}
                    my $centrallat = $a10.'.'.$tmp.$tmp2;
                    my ($tmp,$tmp1) = split '\.',$a13;
                    $tmp2 = substr($tmp1,-1,1);
                    chop $tmp1;
                    
                    if ($tmp1 >= 5) {$tmp++;}
                    my $centrallong = $a12.'.'.$tmp.$tmp2;
                    my $sign;
                    
                    if($northlat =~ /(\d+\.\d+)([NS])/) {
                        ($northlat,$sign)=($1,$2);
                        $northlat *= -1 if $sign =~ /s/i;
                    }
                    $northlat *= 1;
                    $northlat = sprintf("% 6.2f",$northlat);
                    
                    if($northlong =~ /(\d+\.\d+)([WE])/) {
                        ($northlong,$sign)=($1,$2);
                        $northlong *= -1 if $sign =~ /w/i;
                    }
                    $northlong *= 1;
                    $northlong = sprintf("% 6.2f",$northlong);
                    
                    if($southlat =~ /(\d+\.\d+)([NS])/) {
                        ($southlat,$sign)=($1,$2);
                        $southlat *= -1 if $sign =~ /s/i;
                    }
                    $southlat *= 1;
                    $southlat = sprintf("% 6.2f",$southlat);
                    
                    if($southlong =~ /(\d+\.\d+)([WE])/) {
                        ($southlong,$sign)=($1,$2);
                        $southlong *= -1 if $sign =~ /w/i;
                    }
                    $southlong *= 1;
                    $southlong = sprintf("% 6.2f",$southlong);
                    
                    if($centrallat =~ /(\d+\.\d+)([NS])/) {
                        ($centrallat,$sign)=($1,$2);
                        $centrallat *= -1 if $sign =~ /s/i;
                    }
                    $centrallat *= 1;
                    $centrallat = sprintf("% 6.2f",$centrallat);
                    
                    if($centrallong =~ /(\d+\.\d+)([WE])/) {
                        ($centrallong,$sign)=($1,$2);
                        $centrallong *= -1 if $sign =~ /w/i;
                    }
                    $centrallong *= 1;
                    $centrallong = sprintf("% 6.2f",$centrallong);
                    
                    print ".";
                    printf MF "%03d,%02d:%02d, $northlat, $northlong, $centrallat, $centrallong, $southlat, $southlong,\n",$recounter,$hour,$min;
                }
            }
        }
        print "\nFilled Data Set #$recounter\n";
        
        $recounter++;
    }
    
    close MF;
}

sub readineclipseindex () {
    open (MF, "<$eclipse_data_file");
    my $datatype;
    my $counter = 0;
    
    while (<MF>) {
        foreach (split "\n" ) {
            my ($data1, $data2, $data3, $data4, $data5, $data6, $data7, $data8) = split ",";
            if ($data1 =~ /DATA/) {
                $datatype = DATA;
            }
            elsif ($data1 =~ /TRACK/) {
                $datatype = TRACK;
            }
            elsif ($data1 =~ /#/) {
                $datatype = COMMENT;
            }
            else {}
            
            if ($datatype eq COMMENT) {}
            
            if ($datatype eq DATA) {
                if ($data1 =~ /DATA/) {}
                else {
                    push @eclipsedata, {
                        'dayofmonth'     => $data1,
                        'monthtxt'       => $data2,
                        'year'           => $data3,
                        'type'           => $data4,
                        'saros'          => $data5,
                        'eclmag'         => $data6,
                        'duration'       => $data7,
                        'detail'         => $data8,
                    };
                    #print "$data1, $data2, $data3, $data4, $data5, $data6, $data7, $data8\n";
                    
                    $counter++;
                }
            }
        }
    }
    
    close MF;
    return $counter;
}

sub readineclipsetrack () {
    my($dataset) = @_;
    open (MF, "<$eclipse_data_file");
    my $datatype;
    my $counter = 0;
    
    while (<MF>) {
        foreach (split "\n" ) {
            my ($data1, $data2, $data3, $data4, $data5, $data6, $data7, $data8) = split ",";
            if ($data1 =~ /DATA/) {
                $datatype = DATA;
            }
            elsif ($data1 =~ /TRACK/) {
                $datatype = TRACK;
            }
            elsif ($data1 =~ /#/) {
                $datatype = COMMENT;
            }
            
            if ($datatype eq COMMENT) {};
            if ($datatype eq DATA) {}
            if ($datatype eq TRACK) {
                $dataset = sprintf("%03d",$dataset);
                #print "$data1, $dataset\n";
                if ($data1 eq $dataset) {
                    if ($data1 =~ /TRACK/) {}
                    else {
                        my ($hour, $min) = split ":",$data2;
                        
                        push @eclipsetrack, {
                            'hour'           => $hour,
                            'minute'         => $min,
                            'nlat'           => $data3,
                            'nlong'          => $data4,
                            'slat'           => $data7,
                            'slong'          => $data8,
                            'clat'           => $data5,
                            'clong'          => $data6,
                        };
                        #print "$counter: $hour:$min, $data3, $data4, $data5, $data6, $data7, $data8\n";
                        
                        $counter++;
                    }
                }
            }
        }
    }
    
    close MF;
    return $counter;
}

sub datacurrent () {
    my ($counter) = @_;
    my $notice = $settings->{'EclipseNotifyTimeHours'}*3600;
    my $recounter = 0;
    my $monthnum;
    my $next_eclipse;
    my $time_now;
    
    while ($recounter < $counter) {
        $monthnum = num_of_month($eclipsedata[$recounter]->{'monthtxt'});
        $next_eclipse = timelocal(59,59,23,$eclipsedata[$recounter]->{'dayofmonth'},$monthnum,$eclipsedata[$recounter]->{'year'});
        $time_now = time;
        
        if ($time_now < $next_eclipse) {
            $result = $next_eclipse-$time_now;
            
            if (($next_eclipse-$time_now) < $notice ) {
                return $recounter;
            }
            else {
                # CHANGE THIS VALUE AFTER TESTING!
                return NONE;
            }
        }
        
        
        $recounter++;
    }
}

sub writeouteclipsemarker() {
    my ($counter) = @_;
    my $recounter = 1;
    
    if ($counter =~ /FAILED/) {}
    else {
        my $openfile = Eclipse;
        open (MF, ">$eclipse_marker_file");
        &file_header($openfile);
        printf MF "$eclipsetrack[1]->{'clat'}$eclipsetrack[1]->{'clong'} \"%02d:%02d\" color=Grey align=left\n",$eclipsetrack[1]->{'hour'}, $eclipsetrack[1]->{'minute'};
        printf MF "$eclipsetrack[($counter-1)]->{'clat'}$eclipsetrack[($counter-1)]->{'clong'} \"%02d:%02d\" color=Grey align=right\n",$eclipsetrack[($counter-1)]->{'hour'}, $eclipsetrack[($counter-1)]->{'minute'};

        while ($recounter < $counter) {
            if ($eclipsetrack[$recounter]->{'minute'} =~ /[240]0/) {
                printf MF "$eclipsetrack[$recounter]->{'clat'}$eclipsetrack[($recounter)]->{'clong'} \"%02d:%02d\" color=Grey align=top symbolsize=4\n",$eclipsetrack[($recounter)]->{'hour'}, $eclipsetrack[($recounter)]->{'minute'};
                $recounter++;
            }
            
            $recounter++;
        }
    }
    
    close MF;
}

sub writeouteclipsearcboarder () {
    my ($counter) = @_;
    my $recounter = 1;
    
    if ($counter =~ /FAILED/) {}
    else {
        my $openfile = Eclipse;
        open (MF, ">>$eclipse_arc_file");
        print MF "\n\n# Northern Limit Track\n";
        
        while  ($recounter < $counter) {
            if (($recounter+1) != $counter) {
                print MF "$eclipsetrack[$recounter]->{'nlat'}$eclipsetrack[$recounter]->{'nlong'}$eclipsetrack[$recounter+1]->{'nlat'}$eclipsetrack[$recounter+1]->{'nlong'} color=Grey spacing=0.2\n";
            }
            $recounter++
        }
        
        $recounter  = 1;
        print MF "\n\n# Southern Limit Track\n";
        while  ($recounter < $counter) {
            if (($recounter+1) != $counter) {
                print MF "$eclipsetrack[$recounter]->{'slat'}$eclipsetrack[$recounter]->{'slong'}$eclipsetrack[$recounter+1]->{'slat'}$eclipsetrack[$recounter+1]->{'slong'} color=Grey spacing=0.2\n";
            }
            $recounter++
        }
        close MF;
    }
}

sub writeouteclipsearccenter () {
    my ($counter) = @_;
    my $recounter = 1;
    
    if ($counter =~ /FAILED/) {}
    else {
        my $openfile = Eclipse;
        open (MF, ">$eclipse_arc_file");
        &file_header($openfile);
        print MF "# Central Track\n";
        
        while  ($recounter < $counter) {
            if (($recounter+1) != $counter) {
                print MF "$eclipsetrack[$recounter]->{'clat'}$eclipsetrack[$recounter]->{'clong'}$eclipsetrack[$recounter+1]->{'clat'}$eclipsetrack[$recounter+1]->{'clong'} color=Black spacing=0.2\n";
            }
            $recounter++;
        }
        close MF;
    }
}

sub writeouteclipsefilesnone() {
    open (MF, ">$eclipse_marker_file");
    my $openfile = Eclipse;
    &file_header($openfile);
    close MF;
    open (MF, ">$eclipse_arc_file");
    &file_header($openfile);
    close MF;
}

sub writeouteclipselabel() {
    my ($record_number,$track_number,$countdown) = @_;
    $countdown *= 1;
    my $answer;
    $answer = ($countdown / 3600 );
    my ($hours,$ignore) = split('\.',$answer);
    $countdown = ($countdown-($hours*3600));
    $answer = ($countdown / 60 );
    my ($minutes,$ignore) = split('\.',$answer);
    #print "countdown = $countdown, hours = $hours, min = $min\n";
    my $biggestlat = $eclipsetrack[1]->{'clat'};
    my $smallestlat = $eclipsetrack[1]->{'clat'};
    my $biggestlong = $eclipsetrack[1]->{'clong'};
    my $smallestlong = $eclipsetrack[1]->{'clong'};
    my $counter = 2;
    
    while ($counter < ($track_number+1)) {
        if ($biggestlat < $eclipsetrack[$counter]->{'clat'}) {
            $biggestlat = $eclipsetrack[$counter]->{'clat'};
        }
        if ($smallestlat > $eclipsetrack[$counter]->{'clat'}) {
            $smallestlat = $eclipsetrack[$counter]->{'clat'};
        }
        if ($biggestlong < $eclipsetrack[$counter]->{'clong'}) {
            $biggestlong = $eclipsetrack[$counter]->{'clong'};
        }
        if ($smallestlong > $eclipsetrack[$counter]->{'clong'}) {
            $smallestlong = $eclipsetrack[$counter]->{'clong'};
        }
        $counter++;
    }
    
    my $lat = ($biggestlat + $smallestlat) / 2;
    my $long = ($biggestlong + $smallestlong) / 2;
    
    open(MF, ">>$eclipse_marker_file");
    printf MF "\n\n-55 1 \"A$eclipsedata[$record_number]->{'type'} Eclipse will be occuring in $hours hours and $minutes minutes, starting at $eclipsedata[$record_number]->{'dayofmonth'} $eclipsedata[$record_number]->{'monthtxt'} $eclipsedata[$record_number]->{'year'} %02d:%02d GMT\" color=White image=none position=pixel\n",$eclipsetrack[1]->{'hour'},$eclipsetrack[1]->{'minute'};
    print MF "-45 1 \"To view this the best loaction is Latitude $lat ,Longitude $long,\" color=White image=none position=pixel\n";
    print MF "-35 1 \"The Eclipse Track has been put on the map, and will remain until the eclipse has passed.\" color=White image=none position=pixel\n";
    close MF;
}

sub refinedata() {
    my ($record_number) = @_;
    my $counter = 0;
    my $recounter = 0;
    my $linecounter = 0;
    my $datac = 0;
    my $flag = 0;
    my $updatefile = "http://www.wizabit.eclipse.co.uk/xplanet/files/local/update.data";
    my $updateddata = get_webpage($updatefile);
    
    if ($updatedata =~ /FAILED/) {}
    else {
        foreach (split "\n",$updateddata) {
            my ($t1,$t2,$nlat,$nlong,$clat,$clong,$slat,$slong) = split ",";
            
            if ($t1 =~ /(\d\d)(\w\w\w)(\d\d\d\d)/) {
                my ($day,$month,$year) = ($1,$2,$3);
                my ($hour,$minute) = split ":",$t2;
                
                $clong = sprintf("% 6.2f",$clong);
                $clat = sprintf("% 6.2f",$clat);
                $slong = sprintf("% 6.2f",$slong);
                $slat = sprintf("% 6.2f",$slat);
                $nlong = sprintf("% 6.2f",$nlong);
                $nlat = sprintf("% 6.2f",$nlat);
                
                push @eclipserefined, {
                    'day'       => $day,
                    'month'     => $month,
                    'year'      => $year,
                    'hour'      => $hour,
                    'minute'    => $minute,
                    'nlat'      => $nlat,
                    'nlong'     => $nlong,
                    'clat'      => $clat,
                    'clong'     => $clong,
                    'slat'      => $slat,
                    'slong'     => $slong,
                };
                $counter++;
            }
        }
        
        open (MF, "<$eclipse_data_file");
        while (<MF>) {
            foreach (split "\n",) {
                my ($data1,$data2,$data3,$data4,$data5,$data6,$data7,$data8) = split ",";
                @eclipsetempfile;
                
                push @eclipsetempfile, {
                    'element1'        => $data1,
                    'element2'        => $data2,
                    'element3'        => $data3,
                    'element4'        => $data4,
                    'element5'        => $data5,
                    'element6'        => $data6,
                    'element7'        => $data7,
                    'element8'        => $data8,
                };
                $recounter++;
            }
        }
        close MF;
        
        substr($eclipsedata[$record_number]->{'monthtxt'},0,1) = "";
        substr($eclipsedata[$record_number]->{'year'},0,1) = "";
        #print "$eclipserefined[0]->{'day'}:$eclipsedata[$record_number]->{'dayofmonth'} and $eclipserefined[0]->{'month'}:$eclipsedata[$record_number]->{'monthtxt'} and $eclipserefined[0]->{'year'}:$eclipsedata[$record_number]->{'year'}";
        
        if ($eclipserefined[0] -> {'day'} eq $eclipsedata[$record_number] -> {'dayofmonth'} && $eclipserefined[0] -> {'month'} eq $eclipsedata[$record_number] -> {'monthtxt'} && $eclipserefined[0] -> {'year'} eq $eclipsedata[$record_number] -> {'year'}) {
            open (MF, ">$eclipse_data_file");
            $tsn = localtime(time);
            print MF "\#\n\# Last Updated: $tsn\n\#\n";
            $eclipsedata[$record_number]->{'detail'} = INT;
            
            while ($linecounter < $recounter) {
                if ($eclipsetempfile[$linecounter]->{'element1'} =~ /\#/) {
                    $flag = 2;
                }
                
                if ($eclipsetempfile[$linecounter]->{'element1'} =~ /\[DATA/) {
                    $flag = 3;
                }
                
                if ($eclipsetempfile[$linecounter]->{'element1'} =~ /\[TRACK/) {
                    my ($tmp1,$tmp2) = split "]",$eclipsetempfile[$linecounter]->{'element2'};
                    chop $tmp2;
                    chop $tmp2;
                    
                    if ($tmp1 eq $record_number) {
                        $flag = 1;
                    }
                    else {
                        $flag = 5;
                    }
                }
                
                if ($flag eq 0) {
                    print MF "$eclipsetempfile[$linecounter]->{'element1'},$eclipsetempfile[$linecounter]->{'element2'},$eclipsetempfile[$linecounter]->{'element3'},$eclipsetempfile[$linecounter]->{'element4'},$eclipsetempfile[$linecounter]->{'element5'},$eclipsetempfile[$linecounter]->{'element6'},$eclipsetempfile[$linecounter]->{'element7'},$eclipsetempfile[$linecounter]->{'element8'}\n";
                }
                elsif ($flag eq 1) {
                    print MF "$eclipsetempfile[$linecounter]->{'element1'},$eclipsetempfile[$linecounter]->{'element2'}\n";
                    
                    while ($datac < $counter) {
                        printf MF "%03d,$eclipserefined[$datac]->{'hour'}:$eclipserefined[$datac]->{'minute'}, $eclipserefined[$datac]->{'nlat'}, $eclipserefined[$datac]->{'nlong'}, $eclipserefined[$datac]->{'clat'}, $eclipserefined[$datac]->{'clong'}, $eclipserefined[$datac]->{'slat'}, $eclipserefined[$datac]->{'slong'}\n",$record_number;
                        $datac++;
                    }
                    $flag = 2;
                }
                elsif ($flag eq 2) {}
                elsif ($flag eq 4) {
                    substr($eclipsetempfile[$linecounter]->{'element2'},0,1) = "";
                    substr($eclipsetempfile[$linecounter]->{'element3'},0,1) = "";
                    if ($eclipserefined[0]->{'day'} eq $eclipsetempfile[$linecounter]->{'element1'} && $eclipserefined[0]->{'month'} eq $eclipsetempfile[$linecounter]->{'element2'} && $eclipserefined[0]->{'year'} eq $eclipsetempfile[$linecounter]->{'element3'}) {
                        print MF "$eclipsetempfile[$linecounter]->{'element1'},$eclipsetempfile[$linecounter]->{'element2'},$eclipsetempfile[$linecounter]->{'element3'},$eclipsetempfile[$linecounter]->{'element4'},$eclipsetempfile[$linecounter]->{'element5'},$eclipsetempfile[$linecounter]->{'element6'},$eclipsetempfile[$linecounter]->{'element7'}, INTER\n";
                    }
                    else {
                        print MF "$eclipsetempfile[$linecounter]->{'element1'},$eclipsetempfile[$linecounter]->{'element2'},$eclipsetempfile[$linecounter]->{'element3'},$eclipsetempfile[$linecounter]->{'element4'},$eclipsetempfile[$linecounter]->{'element5'},$eclipsetempfile[$linecounter]->{'element6'},$eclipsetempfile[$linecounter]->{'element7'},$eclipsetempfile[$linecounter]->{'element8'}\n";
                    }
                }
                elsif ($flag eq 3) {
                    print MF "$eclipsetempfile[$linecounter]->{'element1'}\n";
                    $flag = 4;
                }
                elsif ($flag eq 5) {
                    print MF "$eclipsetempfile[$linecounter]->{'element1'}$eclipsetempfile[$linecounter]->{'element2'}\n";
                    $flag = 0;
                }
                
                $linecounter++;
            }
        }
        close MF;
    }
}

sub get_settings () {
    open (MF, "<$settings_ini_file");
    while (<MF>) {
        foreach (split "\n") {
            my ($setting,$result) = split "=",$_,2;
            s/([a-z])([A-Z])/$1:$2/g;
            my ($data1,$tmp1) = split ":",$_,2;
            #print "Setting = $setting, Result = $result, Data1 = $data1, Tmp1 = $tmp1\n";
            
            if ($data1 =~ /Quake/) {
                if ($setting =~ /QuakeDetailColorMin/) {$quakesettings->{'QuakeDetailColorMin'} = $result;}
                elsif ($setting =~ /QuakeDetailColorInt/) {$quakesettings->{'QuakeDetailColorInt'} = $result;}
                elsif ($setting =~ /QuakeDetailColorMax/) {$quakesettings->{'QuakeDetailColorMax'} = $result;}
                elsif ($setting =~ /QuakeDetailAlign/) {$quakesettings->{'QuakeDetailAlign'} = $result;}
                elsif ($setting =~ /QuakeCircleColor/) {$quakesettings->{'QuakeCircleColor'} = $result;}
                elsif ($setting =~ /QuakePixelMax/) {$quakesettings->{'QuakePixelMax'} = $result;}
                elsif ($setting =~ /QuakePixelMin/) {$quakesettings->{'QuakePixelMin'} = $result;}
                elsif ($setting =~ /QuakePixelFactor/) {$quakesettings->{'QuakePixelFactor'} = $result;}
                elsif ($setting =~ /QuakeImageTransparent/) {$quakesettings->{'QuakeImageTransparent'} = $result;}
                elsif ($setting =~ /QuakeImageList/) {$quakesettings->{'QuakeImageList'} = $result;}
                elsif ($setting =~ /QuakeDetailColor/) {$quakesettings->{'QuakeDetailColor'} = $result;}
                elsif ($setting =~ /QuakeDetailList/) {$quakesettings->{'QuakeDetailList'} = $result;}
                elsif ($setting =~ /QuakeMinimumSize/) {$quakesettings->{'QuakeMinimumSize'} = $result;}
                elsif ($setting =~ /QuakeReportingDuration/) {$quakesettings->{'QuakeReportingDuration'} = $result;}
                elsif ($setting =~ /QuakeReportingSize/) {$quakesettings->{'QuakeReportingSize'} = $result;}
                elsif ($setting =~ /QuakeFade/) {$quakesettings->{'QuakeFade'} = $result;}						
            }
            
            if ($data1 =~ /Volcano/) {
                if ($setting =~ /VolcanoCircleSizeInner/) {$volcanosettings->{'VolcanoCircleSizeInner'} = $result;}
                elsif ($setting =~ /VolcanoCircleSizeMiddle/) {$volcanosettings->{'VolcanoCircleSizeMiddle'} = $result;}
                elsif ($setting =~ /VolcanoCircleSizeOuter/) {$volcanosettings->{'VolcanoCircleSizeOuter'} = $result;}
                elsif ($setting =~ /VolcanoCircleColorInner/) {$volcanosettings->{'VolcanoCircleColorInner'} = $result;}
                elsif ($setting =~ /VolcanoCircleColorMiddle/) {$volcanosettings->{'VolcanoCircleColorMiddle'} = $result;}
                elsif ($setting =~ /VolcanoCircleColorOuter/) {$volcanosettings->{'VolcanoCircleColorOuter'} = $result;}
                elsif ($setting =~ /VolcanoNameOnOff/) {$volcanosettings->{'VolcanoNameOnOff'} = $result;}
                elsif ($setting =~ /VolcanoNameColor/) {$volcanosettings->{'VolcanoNameColor'} = $result;}
                elsif ($setting =~ /VolcanoNameAlign/) {$volcanosettings->{'VolcanoNameAlign'} = $result;}
                elsif ($setting =~ /VolcanoImageTransparent/) {$volcanosettings->{'VolcanoImageTransparent'} = $result;}
                elsif ($setting =~ /VolcanoImageList/) {$volcanosettings->{'VolcanoImageList'} = $result;}
                elsif ($setting =~ /VolcanoDetailAlign/) {$volcanosettings->{'VolcanoDetailAlign'} = $result;}
                elsif ($setting =~ /VolcanoDetailList/) {$volcanosettings->{'VolcanoDetailList'} = $result;}
                elsif ($setting =~ /VolcanoDetailColor/) {$volcanosettings->{'VolcanoDetailColor'} = $result;}
            }
            
            if ($data1 =~ /Storm/) {
                if ($setting =~ /StormColorTrackReal/) {$stormsettings->{'StormColorTrackReal'} = $result;}
                elsif ($setting =~ /StormColorTrackPrediction/) {$stormsettings->{'StormColorTrackPrediction'} = $result;}
                elsif ($setting =~ /StormColorName/) {$stormsettings->{'StormColorName'} = $result;}
                elsif ($setting =~ /StormColorDetail/) {$stormsettings->{'StormColorDetail'} = $result;}
                elsif ($setting =~ /StormAlignName/) {$stormsettings->{'StormAlignName'} = $result;}
                elsif ($setting =~ /StormAlignDetail/) {$stormsettings->{'StormAlignDetail'} = $result;}
                elsif ($setting =~ /StormImageTransparent/) {$stormsettings->{'StormImageTransparent'} = $result;}
                elsif ($setting =~ /StormImageList/) {$stormsettings->{'StormImageList'} = $result;}
                elsif ($setting =~ /StormDetailAlign/) {$stormsettings->{'StormDetailAlign'} = $result;}
                elsif ($setting =~ /StormDetailList/) {$stormsettings->{'StormDetailList'} = $result;}
                elsif ($setting =~ /StormTrackOnOff/) {$stormsettings->{'StormTrackOnOff'} = $result;}
                elsif ($setting =~ /StormNameOnOff/) {$stormsettings->{'StormNameOnOff'} = $result;}
            }
            
            if ($data1 =~ /Eclipse/) {
                if ($setting =~ /EclipseOnOff/) {$settings->{'EclipseOnOff'} = $result;}
                elsif ($setting =~ /EclipseNotifyOnOff/) {$settings->{'EclipseNotifyOnOff'} = $result;}
                elsif ($setting =~ /EclipseNotifyTimeHours/) {$settings->{'EclipseNotifyTimeHours'} = $result;}
            }
            
            if ($data1 =~ /Norad/) {
                if ($setting =~ /NoradIssImage/) {$noradsettings->{'NoradIssImage'} = $result;}
                elsif ($setting =~ /NoradIssText/) {$noradsettings->{'NoradIssText'} = $result;}
                elsif ($setting =~ /NoradIssDetail/) {$noradsettings->{'NoradIssDetail'} = $result;}
                elsif ($setting =~ /NoradIssOnOff/) {$noradsettings->{'NoradIssOnOff'} = $result;}
                elsif ($setting =~ /NoradHstImage/) {$noradsettings->{'NoradHstImage'} = $result;}
                elsif ($setting =~ /NoradHstText/) {$noradsettings->{'NoradHstText'} = $result;}
                elsif ($setting =~ /NoradHstDetail/) {$noradsettings->{'NoradHstDetail'} = $result;}
                elsif ($setting =~ /NoradHstOnOff/) {$noradsettings->{'NoradHstOnOff'} = $result;}
                elsif ($setting =~ /NoradSoyuzImage/) {$noradsettings->{'NoradSoyuzImage'} = $result;}
                elsif ($setting =~ /NoradSoyuzText/) {$noradsettings->{'NoradSoyuzText'} = $result;}
                elsif ($setting =~ /NoradSoyuzDetail/) {$noradsettings->{'NoradSoyuzDetail'} = $result;}
                elsif ($setting =~ /NoradSoyuzOnOff/) {$noradsettings->{'NoradSoyuzOnOff'} = $result;}
                elsif ($setting =~ /NoradStsImage/) {$noradsettings->{'NoradStsImage'} = $result;}
                elsif ($setting =~ /NoradStsText/) {$noradsettings->{'NoradStsText'} = $result;}
                elsif ($setting =~ /NoradStsDetail/) {$noradsettings->{'NoradStsDetail'} = $result;}
                elsif ($setting =~ /NoradStsOnOff/) {$noradsettings->{'NoradStsOnOff'} = $result;}
                elsif ($setting =~ /NoradSatImage/) {$noradsettings->{'NoradSatImage'} = $result;}
                elsif ($setting =~ /NoradSatText/) {$noradsettings->{'NoradSatText'} = $result;}
                elsif ($setting =~ /NoradSatDetail/) {$noradsettings->{'NoradSatDetail'} = $result;}
                elsif ($setting =~ /NoradSatOnOff/) {$noradsettings->{'NoradSatOnOff'} = $result;}
                elsif ($setting =~ /NoradTleNumbers/) {$noradsettings->{'NoradTleNumbers'} = $result;}
                elsif ($setting =~ /NoradMiscOnOff/) {$noradsettings->{'NoradMiscOnOff'} = $result;}
                elsif ($setting =~ /NoradMiscDetail/) {$noradsettings->{'NoradMiscDetail'} = $result;}
                elsif ($setting =~ /NoradFileName/) {$noradsettings->{'NoradFileName'} = $result;}
            }
            
            if ($data1 =~ /Label/) {
                if ($setting =~ /LabelWarningQuake/) {$labelsettings->{'LabelWarningQuake'} = $result;}
                elsif ($setting =~ /LabelWarningVolcano/) {$labelsettings->{'LabelWarningVolcano'} = $result;}
                elsif ($setting =~ /LabelWarningStorm/) {$labelsettings->{'LabelWarningStorm'} = $result;}
                elsif ($setting =~ /LabelWarningNorad/) {$labelsettings->{'LabelWarningNorad'} = $result;}
                elsif ($setting =~ /LabelWarningCloud/) {$labelsettings->{'LabelWarningCloud'} = $result;}
                elsif ($setting =~ /LabelColorOk/) {$labelsettings->{'LabelColorOk'} = $result;}
                elsif ($setting =~ /LabelColorWarn/) {$labelsettings->{'LabelColorWarn'} = $result;}
                elsif ($setting =~ /LabelColorError/) {$labelsettings->{'LabelColorError'} = $result;}
                elsif ($setting =~ /LabelOnOff/) {$labelsettings->{'LabelOnOff'} = $result;}
            }
            
            if ($data1 =~ /Easter/) {
                if ($setting =~ /EasterEggSurprises/) {$settings->{'EasterEggSurprises'} = $result;}
            }
            
            if ($data1 =~ /Misc/) {
                if ($setting =~ /MiscXplanetVersion1OrBetter/) {$settings->{'XplanetVersion'} = $result;}
            }
            
            if ($data1 =~ /Cloud/) {
                if ($setting =~ /CloudRemoteImageName/) {$cloudsettings->{'CloudRemoteImageName'} = $result;}
                elsif ($setting =~ /CloudLocalImageName/) {$cloudsettings->{'CloudLocalImageName'} = $result;}
                elsif ($setting =~ /UseFreeCloudImage/) {$cloudsettings->{'UseFreeCloudImage'} = $result;}
                elsif ($setting =~ /SubcribedToXplanetClouds/) {$cloudsettings->{'SubcribedToXplanetClouds'} = $result;}
                elsif ($setting =~ /CloudUsername/) {$cloudsettings->{'Username'} = $result;}
                elsif ($setting =~ /CloudPassword/) {$cloudsettings->{'Password'} = $result;}
                elsif ($setting =~ /DirectDownload/) {$cloudsettings->{'DirectDownload'} = $result;}
            }
        }
    }
    
    close MF;
}

sub easteregg () {
    if ($mon == 11) {
        if ($mday == 23) {
            open (MF, ">>$label_file");
            my $start_lat;
            my $start_long;
            my $lat_diff;
            my $long_diff;
            my $journey;
            my $latinc;
            my $longinc;
            my $santa_image_file = "$xplanet_images_dir/santa.png";
            my ($sec,$min,$hour,$mday,$mon,$year,$wday,$yday,$isdst) = gmtime(time);
            -e $santa_image_file || &get_file(santa.png);
            
            if ($hour > 10 ) {
                #Route NP -> Wellington
                if ($hour == 11) {
                    $start_lat = 90;
                    $start_long = 180;
                    $lat_diff = -131;
                    $long_diff = -6;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Wellington -> Sydney
                elsif ($hour == 12) {
                    $start_lat = -41;
                    $start_long = 175;
                    $lat_diff = 7;
                    $long_diff = -23;
                    $journey = 120;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                elsif ($hour == 13) {
                    $start_lat = -41;
                    $start_long = 175;
                    $lat_diff = 7;
                    $long_diff = -23;
                    $journey = 120;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + (($min+60)*$latinc);
                    $slongloc = $start_long + (($min+60)*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Sydney -> Tokyo
                elsif ($hour == 14) {
                    $start_lat = -34;
                    $start_long = 151;
                    $lat_diff = 70;
                    $long_diff = -11;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Tokyo -> Hong Kong
                elsif ($hour == 15) {
                    $start_lat = 36;
                    $start_long = 140;
                    $lat_diff = -13;
                    $long_diff = -26;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Hong Kong -> Bangkok
                elsif ($hour == 16) {
                    $start_lat = 22;
                    $start_long = 114;
                    $lat_diff = -8;
                    $long_diff = -14;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Bangkok -> Calcutta
                elsif ($hour == 17) {
                    $start_lat = 14;
                    $start_long = 101;
                    $lat_diff = 9;
                    $long_diff = -12;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Calcutta -> Karachi
                elsif ($hour == 18) {
                    $start_lat = 23;
                    $start_long = 88;
                    $lat_diff = 2;
                    $long_diff = -21;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Karachi -> Victoria
                elsif ($hour == 19) {
                    $start_lat = 25;
                    $start_long = 67;
                    $lat_diff = -29;
                    $long_diff = -12;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Victoria -> Moscow
                elsif ($hour == 20) {
                    $start_lat = -4;
                    $start_long = 55;
                    $lat_diff = 60;
                    $long_diff = -18;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Moscow -> JoBerg
                elsif ($hour == 21) {
                    $start_lat = 55;
                    $start_long = 38;
                    $lat_diff = -82;
                    $long_diff = -10;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route JoBerg -> Berlin
                elsif ($hour == 22) {
                    $start_lat = -26;
                    $start_long = 28;
                    $lat_diff = 79;
                    $long_diff = -15;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Berlin -> London
                elsif ($hour == 23) {
                    $start_lat = 53;
                    $start_long = 13;
                    $lat_diff = -1;
                    $long_diff = -13;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
            }
        }
        
        if ($mday == 24) {
            open (MF, ">>$label_file");
            my $start_lat;
            my $start_long;
            my $lat_diff;
            my $long_diff;
            my $journey;
            my $latinc;
            my $longinc;
            my $santa_image_file = "$xplanet_images_dir/santa.png";
            my ($sec,$min,$hour,$mday,$mon,$year,$wday,$yday,$isdst) = gmtime(time);
            -e $santa_image_file || &get_file(santa.png);
            
            if ($hour < 12 ) {
                #Route London -> Azores
                if ($hour == 0) {
                    $start_lat = 52;
                    $start_long = 0;
                    $lat_diff = -13;
                    $long_diff = -29;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Azores -> South Georgia
                elsif ($hour == 1) {
                    $start_lat = 39;
                    $start_long = -29;
                    $lat_diff = -93;
                    $long_diff = -8;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route South Georgia -> Rio
                elsif ($hour == 2) {
                    $start_lat = -55;
                    $start_long = -37;
                    $lat_diff = 32;
                    $long_diff = -6;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Rio -> Stanley
                elsif ($hour == 3) {
                    $start_lat = -23;
                    $start_long = -43;
                    $lat_diff = -29;
                    $long_diff = -17;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Stanley -> New York
                elsif ($hour == 4) {
                    $start_lat = -52;
                    $start_long = -60;
                    $lat_diff = 92;
                    $long_diff = -14;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route New York -> Birmingham
                elsif ($hour == 5) {
                    $start_lat = 40;
                    $start_long = -74;
                    $lat_diff = -7;
                    $long_diff = -13;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Birmingham -> Calgary
                elsif ($hour == 6) {
                    $start_lat = 34;
                    $start_long = -87;
                    $lat_diff = 18;
                    $long_diff = -27;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Calgary -> Los Angeles
                elsif ($hour == 7) {
                    $start_lat = 51;
                    $start_long = -114;
                    $lat_diff = -17;
                    $long_diff = -4;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Los Angles -> Sitka
                elsif ($hour == 8) {
                    $start_lat = 34;
                    $start_long = -118;
                    $lat_diff = 23;
                    $long_diff = 17;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Sitka -> Honolulu
                elsif ($hour == 9) {
                    $start_lat = 57;
                    $start_long = -135;
                    $lat_diff = -36;
                    $long_diff = -23;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Hawaii -> Midway Islands
                elsif ($hour == 10) {
                    $start_lat = 21;
                    $start_long = -157;
                    $lat_diff = 7;
                    $long_diff = -20;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
                #Route Midway Islands -> North Pole
                elsif ($hour == 11) {
                    $start_lat = 28;
                    $start_long = -177;
                    $lat_diff = 62;
                    $long_diff = -2.5;
                    $journey = 60;
                    $latinc = $lat_diff / $journey;
                    $longinc = $long_diff / $journey;
                    $slatloc = $start_lat + ($min*$latinc);
                    $slongloc = $start_long + ($min*$longinc);
                    print MF "$slatloc $slongloc \"\" image=santa.png transparent={0,0,0}\n";
                }
            }
        }
    }
    close (MF);
}

$hurricane_on_off = 0;
$volcano_on_off = 0;
$quake_on_off = 0;
$clouds_on_off = 0;
$norad_on_off = 0;
$update_label = 0;
my $hurricane_record_number = 0;
my $volcano_record_number = 0;
my $quake_record_number = 0;
my $norad_record_number = 0;
my $cloud_record_number = 0;

&command_line();
@settings;

&get_settings;
if ($eclipseoverride eq 1) {
    $settings->{'EclipseOnOff'} = Off
}

if ($labelsettings->{'LabelOnOff'} =~ /On/) {
    $label_on_off = 1;
}
else {$label_on_off = 0;}

if ($settings->{'EclipseOnOff'} =~ /On/) {
    $eclipse_on_off = 1;
}
else {$eclipse_on_off = 0;}

if ($settings->{'EasterEggSurprises'} =~ /Off/) {
    $EasterEgg_on_off = 0;
}
else {$EasterEgg_on_off = 1;}

if ($clouds_on_off != 2 && $clouds_on_off != 1 && $volcano_on_off != 1 && $hurricane_on_off != 1 && $quake_on_off != 1 && $norad_on_off != 1 && $update_label != 1 && $installed != 1) {
    &get_it_right_lamer;
}
else {
    if ($clouds_on_off eq 1) {
        $cloud_record_number = 1;
    }
    elsif ($clouds_on_off eq 2) {
        &cloud_update();
        $cloud_record_number = 1;
    }
    
    if ($hurricane_on_off eq 1) {
        my @hurricanedata;
        my @hurricanearcdatafor;
        my @hurricanearcdataact;
        
        $hurricane_record_number = get_hurricanedata;
        &WriteoutHurricane($hurricane_record_number);
        
        my ($actcounter,$forcounter) = get_hurricanearcdata($hurricane_record_number);
        &WriteoutHurricaneArc($hurricane_record_number,$actcounter,$forcounter);
    }
    
    if ($quake_on_off eq 1) {
        my @quakedata;
        
        $quake_record_number = get_quakedata;
        &WriteoutQuake($quake_record_number);
    }
    
    if ($norad_on_off eq 1) {
        my @stsdata;
        my @hstdata;
        my @issdata;
        my @ststimetable;
        
        $norad_record_number = get_noraddata;
    }
    
    if ($volcano_on_off eq 1) {
        my @volcanodata;
        
        # $volcano_record_number = volcanodata_checked;
        $volcano_record_number = get_volcanodata;
        if ($volcano_record_number !~ /what/) {
            &WriteoutVolcano($volcano_record_number); 
        }
    }
    
    if ($label_on_off eq 1) {
        &WriteoutLabel($quake_record_number,$norad_record_number,$cloud_record_number,$hurricane_record_number,$volcano_record_number,0);
    }
    
    if ($update_label eq 1) {
        &WriteoutLabel($quake_record_number,$norad_record_number,$cloud_record_number,$hurricane_record_number,$volcano_record_number,1);
    }
    
    if ($eclipse_on_off eq 1) {
        @eclipsedata;
        @eclipsetrack;
        my $eclipse_record_number = readineclipseindex;
        my $active_eclipse_number = &datacurrent($eclipse_record_number);
        
        if ($active_eclipse_number !~ /NONE/ || $active_eclipse_number !~ /\d/) {
            $active_eclipse_number = NONE;
        }
        #print "Eclipse Record Number = $eclipse_record_number\nActive Eclipse Number = $eclipse_eclipse_number\n";
        
        if ($active_eclipse_number !~ /NONE/) {
            if ($eclipsedata[$active_eclipse_number]->{'detail'} =~ /CRUDE/) {
                @eclipserefined;
                &refinedata($active_eclipse_number);
            }
            
            my $track_number = &readineclipsetrack($active_eclipse_number);
            
            &writeouteclipsearccenter($track_number);
            &writeouteclipsemarker($track_number);
            
            my $next_eclipse = timegm(00,$eclipsetrack[1]->{'minute'},$eclipsetrack[1]->{'hour'},$eclipsedata[$active_eclipse_number]->{'dayofmonth'},num_of_month($eclipsedata[$active_eclipse_number]->{'monthtxt'}),$eclipsedata[$active_eclipse_number]->{'year'});
            my $time_now = time;
            my $countdown = ($next_eclipse-$time_now);
            #print "$countdown\n";
            
            if ($countdown > 0) {
                &writeouteclipsearcboarder($track_number);
            }
            
            if ($settings->{'EclipseNotifyOnOff'} =~ /On/) {
                &writeouteclipselabel($active_eclipse_number,$track_number,$countdown);
            }
        }
        else {
            &writeouteclipsefilesnone;
        }
        
        if ($EasterEgg_on_off !~/0/ && $label_on_off eq 1) {
            &easteregg;
        }
    }
}

#print "ON OFF = $volcano_on_off Volcano Record Number = $volcano_record_number \nON OFF = $quake_on_off Quake Record Number = $quake_record_number\nON OFF = $hurricane_on_off Hurricane Record Number = $hurricane_record_number\nON OFF = $clouds_on_off Cloud Record Number = $cloud_record_number\nON OFF = $norad_on_off NORAD Record Number = $norad_record_number\nON OFF = $label_on_off Label\nON OFF = $eclipse_on_off Eclipse\n";
