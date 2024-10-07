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

Configuration:
--------------
You can configure the behavior using some environment variables:
* _APP_PORT (Optional)_: The TCP porrt where the scoreboard will be listening. Default value is _8080_
* _APP_TITLE (Optional)_: The title of the web page. Default value is _Scoreboard_
* _APP_DEFAULT_LOGO (Optional)_: Image used for no predefined teams. Default is _https://cdn-icons-png.flaticon.com/512/7788/7788863.png_
* _APP_TEAMS (Optional)_: List of predefined teams that can be selected from the configuration. By default only Local and Visitor are defined. The value is a JSON with a map of teams. Key is the name and should contain "icon", "color" and "text_color". Example:
<pre lang="json">
        {
            "Local": {"icon":"https://route-to-icon.png", "color":"#060f8a", "text_color":"#ffffff"},
            "Visitante": {"icon":"https://route-to-icon.png", "color":"#ffffff", "text_color":"#000000"},
        }
</pre>

Running from shell:
-------------------
* Export the environment variables generated before. _UNO_OVERLAY_OID_  is required, the rest are optional
* execute "python main.py"
* nicegui should start a server and open the scoreboard in a browser automatically
Example:
<pre>
  c:\git\remote-scoreboard>SET UNO_OVERLAY_OID=XXXXXXXX
  c:\git\remote-scoreboard>SET UNO_OVERLAY_OUTPUT=https://app.overlays.uno/output/YYYYYYY
  c:\git\remote-scoreboard>python main.py
NiceGUI ready to go on http://localhost:8080, ...
</pre>
Main control:
![imagen](https://github.com/user-attachments/assets/69760288-89fb-40d5-b0f8-c71f9c99e319)
Configuration Panel:
![imagen](https://github.com/user-attachments/assets/8715d96d-e782-4fc1-86a7-903201d7c217)
Overlay:
![imagen](https://github.com/user-attachments/assets/4a0655c2-ed3c-43d4-b9e0-4748bebc1bf1)


Running from docker:
-------------------- 
You can use the docker-compose file by adapting the environment variables required.

Features:
---------
The scoreboard does support the following:
* Points, sets, timeouts and serve managing
* Option to show/hide the overlay
* Option to use simple/full scoreboard (only last game or full list)
* Option to undo game/point/timeout addition
* Configuration page (for managing the overlay look&feel)
* Reset button

Building docker image:
----------------------
There is a Dockerfile template for building your own image and a github action to publish it at docker hub. If you need to do this you should already have the knowledge to adapt and use them.

Internationalization:
---------------------
There is no internationalization support. I used the less text I could and the ones used are in Spanish by default. If you want to translate it for your needs just edit and adapt _messages.py_ file

Disclaimer:
-----------
This software was made without previous design and without proper knowledge of Python, JavaScript and CSS. It was made by testing sample code and adapting and chaining it until the functionality was implemented. There is no proper logging, error handling, internationalization and performance was not polished.

Use it at your own risk.
