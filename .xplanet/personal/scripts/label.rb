#!/usr/bin/env ruby

$xplanet_home = ARGV[0]
$xplanet_temp = ARGV[1]
$marker_label = ARGV[2]
$marker_cloud = ARGV[3]
$marker_quake = ARGV[4]
$marker_storm = ARGV[5]
$marker_volcano = ARGV[6]

pos_lin1 = "-100 -20 "
pos_lin2 = "-85 -20 "
pos_lin3 = "-70 -20 "
pos_lin4 = "-55 -20 "

def create_label_string (marker_f, marker_s, position, marker_o, red_thresh, yellow_thresh)
  temp_string = position
  standard_ending = " image=none position=pixel"

  if File::exists?(marker_f)
    line_color = "Blue"
    ts_o = File::mtime(marker_o)
    ts_n = Time.now
    age = ((ts_n - ts_o)/60/60).to_i

    if (age >= red_thresh)
      line_color = "Red"
    elsif (age < yellow_thresh)
      line_color = "Green"
    else
      line_color = "Yellow"
    end

    timestamp_o = ts_o.strftime("%D at %r")
    timestamp_d = File::mtime(marker_f).strftime("%D at %r")

    temp_string = temp_string + 
      "\"" + 
      marker_s + 
      " updated " +
      timestamp_o + 
      "; downloaded " + 
      timestamp_d + 
      "\" color=" + 
      line_color + 
      standard_ending
  else
    temp_string = temp_string + 
      "\"" + 
      marker_s + 
      " has not been downloaded\" color=Red" + 
      standard_ending
  end

  return temp_string
end

# need to make sure we're pointing to the correct marker files and temp marker files
# and that we've correctly set the upper and lower thresholds
label_file = File.new($xplanet_home+"markers/"+$marker_label, "w")

label_file.puts create_label_string($xplanet_home+"images/"+$marker_cloud, "Cloud Map", pos_lin1, $xplanet_temp+$marker_cloud+".old", 24, 6)
label_file.puts create_label_string($xplanet_home+"markers/"+$marker_quake, "Earthquake Data from TotalMarker", pos_lin2, $xplanet_temp+$marker_quake+".old", 24, 6)
label_file.puts create_label_string($xplanet_home+"markers/"+$marker_storm, "Storm Data from TotalMarker", pos_lin3, $xplanet_temp+$marker_storm+".old", 24, 6)
label_file.puts create_label_string($xplanet_home+"markers/"+$marker_volcano, "Volcano Data from TotalMarker", pos_lin4, $xplanet_temp+$marker_volcano+".old", 120, 48)
###

label_file.close
