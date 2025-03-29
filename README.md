# remote-scoreboard
Self hosted web application developed using nice-gui to remote control some volleyball scoreboards from https://overlays.uno

Pre-requisites:
---------------
* Create an account at https://overlays.uno
* Go to the [this](https://overlays.uno/library/437-Volleyball-Scorebug---Standard) overlay and click on _Add to My Overlays_
* Open your overlay:
    * Copy the current URL and copy the final part of the URL (after _https://app.overlays.uno/control/_). This will be the _UNO_OVERLAY_OID_ 
    * Click on  _Copy Output URL_, this URL will be the _UNO_OVERLAY_OUTPUT_ 
* If you don't want to expose the service to internet you can use the [on air](https://nicegui.io/documentation/section_configuration_deployment#nicegui_on_air) feature from nicegui. Obtain your nicegui on air token and use it as _UNO_OVERLAY_AIR_ID_
* Version 0.2 breaks compatibility with overlays before March 2025

Configuration:
--------------
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
* _ENABLE_MULTITHREAD (Optional)_: If true the uno overlay API will be invoked without waiting for a response so the UI changes inmediatly. Default value is _true_, change to _false_ to wait for API calls to change the UI.
* _LOGGING_LEVEL (Optional)_: Level of logging (debug, info, warning, error). Default value is _warning_.
* _STORAGE_SECRET (Optional)_: Secret for http user data encryption at the browser
* _APP_TEAMS (Optional)_: List of predefined teams that can be selected from the configuration. By default only Local and Visitor are defined. The value is a JSON with a map of teams. Key is the name and should contain "icon", "color" and "text_color". Example:
<pre lang="json">
        {
            "Local": {"icon":"https://cdn-icons-png.flaticon.com/512/8686/8686758.png", "color":"#060f8a", "text_color":"#ffffff"},
            "Visitor": {"icon":"https://cdn-icons-png.flaticon.com/512/8686/8686758.png", "color":"#ffffff", "text_color":"#000000"},
        }
</pre>

Running from shell:
-------------------
* Export the environment variables generated before. _UNO_OVERLAY_OID_  is required to start the scoreboard directly. If not present a dialog will ask for the overlay control URL
* execute "python main.py"
* nicegui should start a server and open the scoreboard in a browser automatically
Example:
<pre>
  c:\git\remote-scoreboard>SET UNO_OVERLAY_OID=XXXXXXXX
  c:\git\remote-scoreboard>SET UNO_OVERLAY_OUTPUT=https://app.overlays.uno/output/YYYYYYY
  c:\git\remote-scoreboard>python main.py
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
The scoreboard does support the following:
* Points, sets, timeouts and serve managing
* Multiple Overlays can be controlled with the same application, use _?control=<token>_ in the URL to update a different overlay. 
* 25 points 5 sets by default. Append _/beach_ to the URL to use 21 points 3 sets configuration.
* Option to show/hide the overlay
* Option to use simple/full scoreboard (only last game or full list)
* Option to undo game/point/timeout addition
* Configuration panel (for managing the overlay look&feel and fullscreen/dark mode)
* Reset button
* Refresh button


Building docker image:
----------------------
There is a Dockerfile template for building your own image and a github action to publish it at docker hub. If you need to do this you should already have the knowledge to adapt and use them.

Internationalization:
---------------------
There is no internationalization support. I used the less text I could. If you want to translate it for your needs just edit and adapt _messages.py_ file


Main control:
-------------------
![imagen](https://github.com/user-attachments/assets/d945dbf3-9a1d-40ed-aaf4-cc012bf41d4c)


-------------------
Configuration Panel:
-------------------
![imagen](https://github.com/user-attachments/assets/0f100ef0-77fa-4f3e-b326-2d8eac7ae14b)

-------------------
Overlay:
-------------------
![imagen](https://github.com/user-attachments/assets/152a586c-1aaa-4c30-b969-c15884097d04)



Disclaimer:
-----------
This software was made without previous design and without proper knowledge of Python, JavaScript and CSS. It was made by testing sample code and adapting and chaining it until the functionality was implemented. There is no proper logging, error handling, internationalization and performance was not polished.

Please keep in mind that there are no users/authentication so do NOT expose directly to internet 

Use it at your own risk.
