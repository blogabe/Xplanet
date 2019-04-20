#!/usr/bin/env ruby

require 'bigdecimal'

quake_min = BigDecimal.new(ARGV[0])
input_file = File.new(ARGV[1], "r")
output_file = File.new(ARGV[2], "w")

while (line = input_file.gets)
  # make sure we're not dealing with a commented line
  if line[0,1] != "#"
    # is the line an earthquake reference
    if line.include? '""'
      # need to grab second line...
      quake_size_line = input_file.gets
      # ... get the quake size...
      /"(.*?)"/.match(quake_size_line)
      quake_size = BigDecimal.new($1)
      # ... and check to see if it meets the min size
      if quake_size >= quake_min
        # write out the quake markers to the marker file
        output_file.puts(line)
        output_file.puts(quake_size_line)
      end
    end
  end
end

input_file.close
output_file.close
