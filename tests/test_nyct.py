from nyct_gtfs import NYCTFeed, Stations, Trip
from datetime import datetime
from typing import List

# Bergen is F20, so want F20N, but it's down so...
# 4 downtown is 626S

# Initialize the feed for a specific line, e.g., the 1 train
feed = NYCTFeed("4")

# Fetch all active trips for the line
bergen_trips = feed.filter_trips(headed_for_stop_id='F20N')

n_trips = feed.filter_trips(travel_direction='S')

# Display information about the first train
# print(bergen_trips[0])
# print(n_trips[0])

lex_trains: List[Trip] = feed.filter_trips(headed_for_stop_id='626S')

for trip in lex_trains:
    # print(trip)
    # stop = trip.headed_to_stop('626S')
    target_stop = next((stop for stop in trip.stop_time_updates if stop.stop_id == '626S'), None)
    if target_stop:
        print(f"Target stop details: {target_stop}")
        print(f"Arrival time: {target_stop.arrival}")


# Your script logic here
print("Script execution complete. Dropping into interactive mode.")

# Start an interactive session
# code.interact(local=locals())