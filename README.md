# Remote Scoreboard

A self-hosted web application to remotely control volleyball scoreboards from [overlays.uno](https://overlays.uno). Developed with [NiceGUI](https://nicegui.io/).

## Features

*   **Remote Control:** Manage points, sets, timeouts, and serves for volleyball matches.
*   **Multi-Overlay Support:** Control multiple overlays with a single application instance.
*   **Customizable Match Rules:** Configure match parameters like points per set and number of sets.
*   **Team Customization:** Define preset teams with custom names, logos, and colors.
*   **User Authentication:** Secure access to the scoreboard with a user management system.
*   **Configuration Panel:** Customize the look and feel of the scoreboard, including dark mode and fullscreen options.
*   **Internationalization:** Support for multiple languages (currently English and Spanish).
*   **Docker Support:** Easily deploy the application using Docker and Docker Compose.

## Prerequisites

1.  Create an account on [overlays.uno](https://overlays.uno).
2.  Add the [Volleyball Scorebug - Standard](https://overlays.uno/library/437-Volleyball-Scorebug---Standard) overlay to your account.
3.  From your overlay page, you will need:
    *   **Overlay OID:** The final part of the control URL (`https://app.overlays.uno/control/{UNO_OVERLAY_OID}`).
    *   **Overlay Output URL:** The URL for the scoreboard output.

## Configuration

The application is configured through environment variables.

| Variable                       | Description                                                                                                                               | Default Value                                                              |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| `UNO_OVERLAY_OID`              | The control token for your overlay. If not provided, a dialog will prompt for it.                                                         | `(none)`                                                                   |
| `UNO_OVERLAY_OUTPUT`           | The output URL for your overlay. Used to display a link in the configuration panel.                                                       | `(none)`                                                                   |
| `APP_PORT`                     | The TCP port for the web server.                                                                                                          | `8080`                                                                     |
| `APP_TITLE`                    | The title of the web page.                                                                                                                | `Scoreboard`                                                               |
| `APP_DARK_MODE`                | Dark mode setting (`on`, `off`, or `auto`).                                                                                               | `auto`                                                                     |
| `APP_DEFAULT_LOGO`             | The default logo for teams without a predefined icon.                                                                                     | `https://cdn-icons-png.flaticon.com/512/7788/7788863.png`                   |
| `MATCH_GAME_POINTS`            | The number of points per set.                                                                                                             | `25`                                                                       |
| `MATCH_GAME_POINTS_LAST_SET`   | The number of points for the last set.                                                                                                    | `15`                                                                       |
| `MATCH_GAME_SETS`              | The number of sets to win the match.                                                                                                      | `5`                                                                        |
| `ORDERED_TEAMS`                | If `true`, the list of teams is shown ordered in the combo box.                                                                           | `true`                                                                     |
| `ENABLE_MULTITHREAD`           | If `true`, the UI updates immediately without waiting for the UNO API response.                                                           | `true`                                                                     |
| `LOGGING_LEVEL`                | The logging level (`debug`, `info`, `warning`, `error`).                                                                                  | `warning`                                                                  |
| `STORAGE_SECRET`               | A secret key for encrypting user data in the browser.                                                                                     | `(none)`                                                                   |
| `SCOREBOARD_LANGUAGE`          | The language for the interface (e.g., `es` for Spanish).                                                                                  | `en`                                                                       |
| `REST_USER_AGENT`              | The User-Agent header sent to the UNO API.                                                                                                | `curl/8.15.0`                                                              |
| `APP_TEAMS`                    | A JSON string defining a map of preset teams with their `icon`, `color`, and `text_color`.                                                | `{"Local": ..., "Visitor": ...}`                                           |
| `SCOREBOARD_USERS`             | A JSON string defining a map of users and their passwords.                                                                                | `(none)`                                                                   |
| `PREDEFINED_OVERLAYS`          | A JSON string defining a map of predefined overlays with their `control` and `output` URLs.                                               | `(none)`                                                                   |
| `HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED` | If `true`, the custom overlay input is hidden when predefined overlays are available.                                               | `false`                                                                    |

## Running the Application

### Local Execution

1.  Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```
2.  Set the required environment variables. For example:
    ```bash
    export UNO_OVERLAY_OID="your_overlay_oid"
    export UNO_OVERLAY_OUTPUT="your_overlay_output_url"
    ```
3.  Run the application:
    ```bash
    python main.py
    ```
4.  Open your browser and navigate to `http://localhost:8080`.

### Docker

1.  Create a `.env` file with your desired configuration. For example:
    ```
    EXTERNAL_PORT=80
    APP_TITLE=MyScoreboard
    UNO_OVERLAY_OID=<overlay control token>
    UNO_OVERLAY_OUTPUT=https://app.overlays.uno/output/<overlay output token>
    ```
2.  Run the application using Docker Compose:
    ```bash
    docker-compose up -d
    ```

## Building the Docker Image

A `Dockerfile` is provided to build a custom Docker image. You can adapt it to your needs. The included GitHub Actions workflow demonstrates how to build and publish the image to Docker Hub.

## Internationalization

To add a new language, implement the language in the `messages.py` file and set the `SCOREBOARD_LANGUAGE` environment variable to the corresponding language code.

## Screenshots

| Login                                                                                             | Overlay Selector                                                                                    | Main Control                                                                                        |
| ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| ![Login Dialog](https://github.com/user-attachments/assets/020f40e0-87b7-452a-bcde-7727c34f34d5)    | ![Overlay Selector](https://github.com/user-attachments/assets/35b94ca2-57b5-4cb9-92ee-269b0317bc35) | ![Main Control](https://github.com/user-attachments/assets/d945dbf3-9a1d-40ed-aaf4-cc012bf41d4c)     |

| Setup Panel                                                                                         | Configuration                                                                                         | Overlay                                                                                             |
| --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| <img width="577" height="292" alt="Setup Panel" src="https://github.com/user-attachments/assets/355a4d89-aece-4fe8-816c-8258968b78f2" /> | <img width="268" height="435" alt="Configuration" src="https://github.com/user-attachments/assets/577db9a9-4f3b-4d70-ac52-dc5da7a11db2" /> | ![Overlay](https://github.com/user-attachments/assets/152a586c-1aaa-4c30-b969-c15884097d04)        |

## Disclaimer

This software was developed as a personal project and is provided "as is" without any warranties. While the authentication feature provides a basic level of security, it is not recommended to expose the application directly to the internet. Use it at your own risk.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.