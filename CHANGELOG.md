# Changelog

## [0.2.0] (13/03/2025)

### Added 
- Add cheer event notification handler
- Getter for subscriber, follower and chatters
- Rules to check if a event can be sub by the account of the broadcaster or an other account

### Fixed
- Add parameter to use database from ChatBot class
- Fix ban, poll end, prediction lock, prediction end trigger callback
- Fix start and end date for poll and prediction for database ingestion
- Fix call trigger callback with no parameter
- Fix insert sql request
- Call all table creation if no database exist
- Fix parameter names of event data in the process message function

### Modified
- Use decorator to check the token's validity

## [0.1.0] (05/03/2024)

### Added

- Add method to get access token with Twitch API
- Add method to refresh access token with Twitch API
- Add ChatBot class
- Add get user id method for ChatBot
- Add check for request on Twitch for ChatBot
- Add get and post request with check for ChatBot
- Add send method for ChatBot
- Event server manage subscription
- Event server manage any subscription
- Store message in a sqlite database
- EventServer trigger message event with ChatBot class
- Add many subscription to receive notification
- Add user action to interact with the chat
- Stream information are stored in a SQLite3 data base
- Add class to standardize twitch right
