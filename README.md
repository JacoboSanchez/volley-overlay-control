# volley-overlay-control
`volley-overlay-control` is a self-hostable web application for controlling volleyball scoreboards from _overlays.uno_. It provides a user-friendly interface to manage all aspects of a volleyball match, including scores, sets, timeouts, and serving teams. The application is highly customizable, allowing you to personalize the look and feel of your scoreboard with team logos, colors, and pre-defined themes. It also supports multiple users and overlays, making it a versatile solution for managing scoreboards for different events.

Pre-requisites:
---------------
*   Python 3.x
*   An account on _overlays.uno_
*   A volleyball scoreboard overlay added to your account from the _overlays.uno_ library.

**Instructions to create an overlay:**
* Login to your _overlays.uno_ account
* Go to the [this](https://overlays.uno/library/437-Volleyball-Scorebug---Standard) overlay and click on _Add to My Overlays_
* Open your overlay:
    * Copy the current URL and copy the final part of the URL (after _https://app.overlays.uno/control/_). This will be the _UNO_OVERLAY_OID_ 
    * Click on  _Copy Output URL_, this URL will be the _UNO_OVERLAY_OUTPUT_ 
* If you don't want to expose the service to internet you can use the [on air](https://nicegui.io/documentation/section_configuration_deployment#nicegui_on_air) feature from nicegui. Obtain your nicegui on air token and use it as _UNO_OVERLAY_AIR_ID_
* Version 0.2 breaks compatibility with overlays before March 2025



Environment variables:
----------------------
You can configure the behavior using some environment variables:
* _UNO_OVERLAY_OID (Optional)_: The control token. If not present a dialog will ask for it.
* _UNO_OVERLAY_OUTPUT (Optional)_: The output URL. Will be used only to show a link for it in the configuration panel. 
* _APP_PORT (Optional)_: The TCP port where the scoreboard will be listening. Default value is _8080_.
* _APP_TITLE (Optional)_: The title of the web page. Default value is _Scoreboard_.
* _APP_DARK_MODE (Optional)_: To specify the dark mode configuration, can be _on_, _off_ or _auto_. Default value is _auto_.
* _APP_DEFAULT_LOGO (Optional)_: Image used for no predefined teams. Default is _https://cdn-icons-png.flaticon.com/512/7788/7788863.png_
* _MATCH_GAME_POINTS (Optional)_: The number of points for each set. Default value is 25.
* _MATCH_GAME_POINTS_LAST_SET (Optional)_: The number of points for the last set. Default value is 15.
* _MATCH_GAME_SETS (Optional)_: The number of sets to win the game. Default value is 5.  
* _ORDERED_TEAMS=(Optional)_: If true the list of teams is shown ordered in the combo box. Default is _true_.
* _ENABLE_MULTITHREAD (Optional)_: If true the uno overlay API will be invoked without waiting for a response so the UI changes inmediatly. Default value is _true_, change to _false_ to wait for API calls to change the UI.
* _LOGGING_LEVEL (Optional)_: Level of logging (debug, info, warning, error). Default value is _warning_.
* _STORAGE_SECRET (Optional)_: Secret for http user data encryption at the browser
* _SCOREBOARD_LANGUAGE (Optional)_: Language code different than english (currently only _es_ implemented.
* _REST_USER_AGENT (Optional)_: User agent header sent to UNO API to avoid Cloudflare bot detection. Default value is _curl/8.15.0_.
* _APP_TEAMS (Optional)_: List of predefined teams that can be selected from the configuration. By default only Local and Visitor are defined. The value is a JSON with a map of teams. Key is the name and should contain "icon", "color" and "text_color". Example:
<pre lang="json">
        {
            "Local": {"icon":"https://cdn-icons-png.flaticon.com/512/8686/8686758.png", "color":"#060f8a", "text_color":"#ffffff"},
            "Visitor": {"icon":"https://cdn-icons-png.flaticon.com/512/8686/8686758.png", "color":"#ffffff", "text_color":"#000000"},
        }
</pre>
* _SCOREBOARD_USERS (Optional)_: List of users allowed. They may include information about the overlay to open automatically with that user. Example:
<pre lang="json">
        {
            "user1": {"password":"password1"},
            "user2": {"password":"password2", "control":"CONTROLTOKEN", "output":"OUTPUTTOKEN"},
        }
</pre>
* _PREDEFINED_OVERLAYS (Optional)_: List of predefined overlays configuration available listed by alias. If configured a combo will be displayed to select one. It may contain a whitelist for users that may select each configuration. Example:
<pre lang="json">
        {
            "Overlay only for user 1":{"control":"CONTROLTOKEN", "output":"OUTPUTTOKEN", "allowed_users":["user1"]},
            "Overlay for all users":{"control":"CONTROLTOKEN", "output":"OUTPUTTOKEN"},
            "Unselectable overlay":{"control":"CONTROLTOKEN", "output":"OUTPUTTOKEN", "allowed_users":[]}
        }
</pre>
* _HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED (Optional)_: If true the input text field to specify an overlay will not be displayed when predefined overlays are configured. Default is false so both the input control URL and predefined overlays options will be displayed.
* _APP_THEMES (Optional)_: List of themes. The content is a json with a map with theme name as key and customization json as value (the same way the UNO overlay API expects). If configured a palette button will be displayed to select one. Example:
<pre lang="json">
        {
            "Change position and show logos theme":{"Height": 10,"Left-Right": -33.5,"Logos": true},
            "Change only game status colors":{"Game Status Color": "#252525","Game Status Text Color": "#ffffff"}
        }
</pre>


Running from shell:
-------------------
* Export the environment variables generated before. _UNO_OVERLAY_OID_  is required to start the scoreboard directly. If not present a dialog will ask for the overlay control URL
* execute "python main.py"
* nicegui should start a server and open the scoreboard in a browser automatically
Example:
<pre>
  c:\git\volley-overlay-control>SET UNO_OVERLAY_OID=XXXXXXXX
  c:\git\volley-overlay-control>SET UNO_OVERLAY_OUTPUT=https://app.overlays.uno/output/YYYYYYY
  c:\git\volley-overlay-control>python main.py
NiceGUI ready to go on http://localhost:8080, ...
</pre>

Running from docker:
--------------------
You can use the docker-compose file by adapting the environment variables required. An example of _.env_ file would be:

<pre>
EXTERNAL_PORT=80
APP_TITLE=MyScoreboard
UNO_OVERLAY_OID=<overlay control token>
UNO_OVERLAY_OUTPUT=https://app.overlays.uno/output/<overlay output token>
</pre>



Features:
---------
*   **Complete Match Control:**
    *   Manage points, sets, and timeouts for both teams.
    *   Indicate the serving team.
    *   Undo functionality for points and timeouts.
    *   Support for both indoor (25 points, 5 sets) and beach volleyball (21 points, 3 sets) modes.
*   **Advanced Customization:**
    *   Customize team names, logos, and colors.
    *   Adjust the scoreboard's dimensions (height, width) and position (horizontal, vertical).
    *   Apply a glossy/gradient effect to the scoreboard.
    *   Show or hide team logos.
    *   Lock team colors and icons to prevent accidental changes.
    *   Create and load custom themes to quickly switch between different styles.
*   **User and Overlay Management:**
    *   Support for multiple users with password protection.
    *   Control multiple overlays from a single instance of the application.
    *   Select from a list of predefined overlays.
*   **User-Friendly Interface:**
    *   Dark mode support (auto, on, off).
    *   Auto-hide the scoreboard during gameplay.
    *   Automatically switch to a simplified view showing only the current set.
    *   Internationalization support (English and Spanish).
*   **Flexible Deployment:**
    *   Run locally as a Python application.
    *   Deploy as a Docker container.
    *   Expose the application to the internet using ngrok-like services.


Building docker image:
----------------------
There is a Dockerfile template for building your own image and a github action to publish it at docker hub. If you need to do this you should already have the knowledge to adapt and use them.

Internationalization:
---------------------
Translations may be added by implementing the language in _messages.py_ file and using the language key with the _SCOREBOARD_LANGUAGE_ environment variable

Login dialog:
-------------------
![imagen](https://github.com/user-attachments/assets/020f40e0-87b7-452a-bcde-7727c34f34d5)


Overlay selector dialog with input text area and predefined overlay selector:
----------------------------------------------------------------------------------
![imagen](https://github.com/user-attachments/assets/35b94ca2-57b5-4cb9-92ee-269b0317bc35)


Main control:
-------------------
![imagen](https://github.com/user-attachments/assets/d945dbf3-9a1d-40ed-aaf4-cc012bf41d4c)


Setup Panel:
-------------------
<img width="577" height="292" alt="imagen" src="https://github.com/user-attachments/assets/355a4d89-aece-4fe8-816c-8258968b78f2" />

Configuration dialog:
---------------
<img width="268" height="435" alt="imagen" src="https://github.com/user-attachments/assets/577db9a9-4f3b-4d70-ac52-dc5da7a11db2" />


Overlay:
-------------------
![imagen](https://github.com/user-attachments/assets/152a586c-1aaa-4c30-b969-c15884097d04)



Disclaimer:
-----------
This software was made without previous design and without proper knowledge of Python, JavaScript and CSS. It was made by testing sample code and adapting and chaining it until the functionality was implemented. There is no proper logging, error handling, internationalization and performance is far from ideal.

Please keep in mind that authentication feature is not secure and only intended to distribute overlays so do NOT expose directly to internet 

Use it at your own risk.
