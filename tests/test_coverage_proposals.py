"""
Tests to bring below-50% coverage modules up to ≥50%.

Coverage targets:
  preview_page.py     19%  →  50%+   (critical gap)
  ws_client.py        54%            (already above 50%, extended here)
  button_style.py     53%            (already above 50%, extended here)
"""
import json
import logging
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from app.app_storage import AppStorage
from app.components.button_style import update_button_style
from app.ws_client import WSControlClient


# ---------------------------------------------------------------------------
# 1. PreviewPage  (19% → 50%+)
# ---------------------------------------------------------------------------

class TestPreviewPage:
    """Tests for app/preview_page.py."""

    @pytest.fixture
    def page(self):
        """Create a PreviewPage with mocked NiceGUI components."""
        with patch('app.preview_page.ui') as mock_ui:
            mock_ui.dark_mode.return_value = MagicMock()
            mock_ui.fullscreen.return_value = MagicMock()
            from app.preview_page import PreviewPage
            p = PreviewPage(output='test_output')
        return p

    # -- scale clamping -------------------------------------------------------

    @pytest.mark.asyncio
    async def test_increase_scale_clamps_at_2(self, page):
        """increase_scale() should not exceed 2.0."""
        page._update_iframe = AsyncMock()
        page.scale_factor = 1.9
        await page.increase_scale()
        assert page.scale_factor == 2.0
        await page.increase_scale()
        assert page.scale_factor == 2.0

    @pytest.mark.asyncio
    async def test_decrease_scale_clamps_at_0_5(self, page):
        """decrease_scale() should not go below 0.5."""
        page._update_iframe = AsyncMock()
        page.scale_factor = 0.6
        await page.decrease_scale()
        assert page.scale_factor == 0.5
        await page.decrease_scale()
        assert page.scale_factor == 0.5

    @pytest.mark.asyncio
    async def test_scale_increases_by_0_2(self, page):
        """increase_scale() should add 0.2 each call."""
        page._update_iframe = AsyncMock()
        page.scale_factor = 1.0
        await page.increase_scale()
        assert page.scale_factor == pytest.approx(1.2)

    @pytest.mark.asyncio
    async def test_scale_decreases_by_0_2(self, page):
        """decrease_scale() should subtract 0.2 each call."""
        page._update_iframe = AsyncMock()
        page.scale_factor = 1.0
        await page.decrease_scale()
        assert page.scale_factor == pytest.approx(0.8)

    # -- _update_iframe guards -----------------------------------------------

    @pytest.mark.asyncio
    async def test_update_iframe_skips_when_already_rendering(self, page):
        """_update_iframe() should be a no-op while _is_rendering is True."""
        page._is_rendering = True
        page.frame_container = MagicMock()
        await page._update_iframe()
        page.frame_container.clear.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_iframe_skips_when_frame_container_none(self, page):
        """_update_iframe() should return early when frame_container is None."""
        page.frame_container = None
        # Should not raise
        await page._update_iframe()

    @pytest.mark.asyncio
    async def test_update_iframe_renders_when_ready(self, page):
        """_update_iframe() clears the container and calls create_iframe_card."""
        page.frame_container = MagicMock()
        page.page_width = 800
        page.page_height = 600
        mock_card = AsyncMock()
        with patch('app.preview_page.create_iframe_card', mock_card):
            await page._update_iframe()
        mock_card.assert_called_once()
        assert page._is_rendering is False

    @pytest.mark.asyncio
    async def test_update_iframe_resets_flag_on_error(self, page):
        """_update_iframe() resets _is_rendering even when create_iframe_card raises."""
        page.frame_container = MagicMock()
        page.page_width = 800
        page.page_height = 600
        with patch('app.preview_page.create_iframe_card',
                   new=AsyncMock(side_effect=RuntimeError("boom"))):
            with pytest.raises(RuntimeError):
                await page._update_iframe()
        assert page._is_rendering is False

    @pytest.mark.asyncio
    async def test_update_iframe_skips_card_when_dimensions_none(self, page):
        """_update_iframe() should not call create_iframe_card when dims are None."""
        page.frame_container = MagicMock()
        page.page_width = None
        page.page_height = None
        mock_card = AsyncMock()
        with patch('app.preview_page.create_iframe_card', mock_card):
            await page._update_iframe()
        mock_card.assert_not_called()
        page.frame_container.clear.assert_called_once()

    # -- create_page ----------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_page_shows_label_when_no_output(self, page):
        """create_page() without an output token should render an error label."""
        page.output = None
        with patch('app.preview_page.ui.label') as mock_label:
            await page.create_page()
        mock_label.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_page_calls_update_iframe_when_dimensions_set(self, page):
        """create_page() calls _update_iframe when page dims are known."""
        page.page_width = 800
        page.page_height = 600
        page._update_iframe = AsyncMock()
        await page.create_page()
        page._update_iframe.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_page_skips_update_iframe_when_no_dimensions(self, page):
        """create_page() should not call _update_iframe when page dims are None."""
        page.page_width = None
        page.page_height = None
        page._update_iframe = AsyncMock()
        await page.create_page()
        page._update_iframe.assert_not_called()

    # -- set_page_size --------------------------------------------------------

    @pytest.mark.asyncio
    async def test_set_page_size_first_call_triggers_create_page(self, page):
        """The first set_page_size() call should call create_page."""
        page.page_height = None
        page.page_width = None
        page.create_page = AsyncMock()
        await page.set_page_size(1920, 1080)
        assert page.page_height == 1080
        assert page.page_width == 1920
        page.create_page.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_page_size_subsequent_call_updates_iframe(self, page):
        """Subsequent set_page_size() calls should call _update_iframe."""
        page.page_height = 600
        page.page_width = 800
        page._update_iframe = AsyncMock()
        await page.set_page_size(1920, 1080)
        page._update_iframe.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_page_size_updates_stored_dimensions(self, page):
        """set_page_size() should always update the stored dimensions."""
        page.page_height = 600
        page.page_width = 800
        page._update_iframe = AsyncMock()
        await page.set_page_size(1920, 1080)
        assert page.page_width == 1920
        assert page.page_height == 1080

    # -- dark mode / customize_buttons ----------------------------------------

    def test_customize_buttons_sets_light_mode_icon_when_dark(self, page):
        """customize_buttons() sets 'light_mode' icon when dark_enabled=True."""
        page.dark_enabled = True
        page.dark_button = MagicMock()
        page.customize_buttons()
        page.dark_button.set_icon.assert_called_with('light_mode')

    def test_customize_buttons_sets_dark_mode_icon_when_light(self, page):
        """customize_buttons() sets 'dark_mode' icon when dark_enabled=False."""
        page.dark_enabled = False
        page.dark_button = MagicMock()
        page.customize_buttons()
        page.dark_button.set_icon.assert_called_with('dark_mode')

    @pytest.mark.asyncio
    async def test_toggle_dark_mode_flips_dark_enabled_to_true(self, page):
        """toggle_dark_mode() should set dark_enabled=True and update icon."""
        page.dark_enabled = False
        page.dark_button = MagicMock()
        page._update_iframe = AsyncMock()
        await page.toggle_dark_mode()
        assert page.dark_enabled is True
        page.dark_button.set_icon.assert_called_with('light_mode')
        page._update_iframe.assert_called_once()

    @pytest.mark.asyncio
    async def test_toggle_dark_mode_flips_dark_enabled_to_false(self, page):
        """toggle_dark_mode() should set dark_enabled=False and update icon."""
        page.dark_enabled = True
        page.dark_button = MagicMock()
        page._update_iframe = AsyncMock()
        await page.toggle_dark_mode()
        assert page.dark_enabled is False
        page.dark_button.set_icon.assert_called_with('dark_mode')

    @pytest.mark.asyncio
    async def test_toggle_dark_mode_calls_dark_mode_set_value(self, page):
        """toggle_dark_mode() should call dark_mode.set_value with the new state."""
        page.dark_enabled = False
        page.dark_button = MagicMock()
        page._update_iframe = AsyncMock()
        await page.toggle_dark_mode()
        page.dark_mode.set_value.assert_called_with(True)

    # -- fullscreen -----------------------------------------------------------

    @pytest.mark.asyncio
    async def test_toggle_fullscreen_calls_toggle(self, page):
        """toggle_fullscreen() should call fullscreen.toggle()."""
        await page.toggle_fullscreen()
        page.fullscreen.toggle.assert_called_once()

    # -- constructor defaults -------------------------------------------------

    def test_default_scale_factor_is_one(self, page):
        """scale_factor should default to 1.0."""
        assert page.scale_factor == 1.0

    def test_default_dark_enabled_is_false(self, page):
        """dark_enabled should default to False."""
        assert page.dark_enabled is False

    def test_default_frame_container_is_none(self, page):
        """frame_container should be None before initialize()."""
        assert page.frame_container is None

    def test_output_stored_on_init(self, page):
        """output should be stored from the constructor argument."""
        assert page.output == 'test_output'


# ---------------------------------------------------------------------------
# 2. WSControlClient – _handle_message, send methods, connect
# ---------------------------------------------------------------------------

class TestWSControlClientMessages:
    """Tests for message handling and send methods in ws_client.py."""

    @pytest.fixture
    def client(self):
        return WSControlClient(
            overlay_id='test_overlay',
            ws_url='ws://localhost:9000/ws/control/test_overlay',
        )

    # -- send helpers ---------------------------------------------------------

    def test_send_returns_false_when_not_connected(self, client):
        """_send() should return False when not connected."""
        assert client.send_state({'score': 0}) is False

    def test_send_state_message_format(self, client):
        """send_state() should build a state_update message."""
        mock_ws = MagicMock()
        client._ws = mock_ws
        client._connected = True
        client.send_state({'score': 1})
        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent['type'] == 'state_update'
        assert sent['payload'] == {'score': 1}

    def test_send_visibility_message_format(self, client):
        """send_visibility() should build a visibility message."""
        mock_ws = MagicMock()
        client._ws = mock_ws
        client._connected = True
        client.send_visibility(True)
        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent['type'] == 'visibility'
        assert sent['show'] is True

    def test_send_get_state_message_format(self, client):
        """send_get_state() should send {"type": "get_state"}."""
        mock_ws = MagicMock()
        client._ws = mock_ws
        client._connected = True
        client.send_get_state()
        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent == {'type': 'get_state'}

    def test_send_raw_config_message_format(self, client):
        """send_raw_config() should wrap the payload correctly."""
        mock_ws = MagicMock()
        client._ws = mock_ws
        client._connected = True
        payload = {'model': {}}
        client.send_raw_config(payload)
        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent['type'] == 'raw_config'
        assert sent['payload'] == payload

    def test_send_marks_disconnected_on_ws_error(self, client):
        """_send() should set _connected=False when ws.send raises."""
        mock_ws = MagicMock()
        mock_ws.send.side_effect = Exception("broken pipe")
        client._ws = mock_ws
        client._connected = True
        result = client._send({'type': 'ping'})
        assert result is False
        assert client._connected is False

    def test_send_returns_true_on_success(self, client):
        """_send() should return True when the message is sent successfully."""
        mock_ws = MagicMock()
        client._ws = mock_ws
        client._connected = True
        result = client._send({'type': 'ping'})
        assert result is True

    # -- _handle_message ------------------------------------------------------

    def test_handle_connected_updates_obs_count(self, client):
        """'connected' message should set obs_client_count."""
        client._handle_message({'type': 'connected', 'protocol': 1,
                                 'obs_clients': 3, 'overlay_id': 'x'})
        assert client.obs_client_count == 3

    def test_handle_connected_protocol_mismatch_logs_warning(self, client):
        """Protocol mismatch should emit a warning."""
        with patch('app.ws_client.logger') as mock_logger:
            client._handle_message({'type': 'connected', 'protocol': 99,
                                     'obs_clients': 0, 'overlay_id': 'x'})
        mock_logger.warning.assert_called_once()

    def test_handle_connected_matching_protocol_no_warning(self, client):
        """Matching protocol version should not emit a warning."""
        with patch('app.ws_client.logger') as mock_logger:
            client._handle_message({'type': 'connected', 'protocol': 1,
                                     'obs_clients': 0, 'overlay_id': 'x'})
        mock_logger.warning.assert_not_called()

    def test_handle_ack_updates_obs_count(self, client):
        """'ack' message should update obs_client_count."""
        client._handle_message({'type': 'ack', 'obs_clients': 5, 'ref': 'abc'})
        assert client.obs_client_count == 5

    def test_handle_obs_event_updates_obs_count(self, client):
        """'obs_event' message should update obs_client_count."""
        client._handle_message({'type': 'obs_event', 'obs_clients': 2, 'event': 'visible'})
        assert client.obs_client_count == 2

    def test_handle_pong_is_noop(self, client):
        """'pong' message should not raise and not change state."""
        client._handle_message({'type': 'pong'})
        assert client.obs_client_count == 0

    def test_handle_state_is_noop(self, client):
        """'state' message should not raise."""
        client._handle_message({'type': 'state', 'data': {}})

    def test_on_event_callback_called_for_all_messages(self, client):
        """on_event callback should fire for every message."""
        callback = MagicMock()
        client._on_event = callback
        msg = {'type': 'pong'}
        client._handle_message(msg)
        callback.assert_called_once_with(msg)

    def test_on_event_callback_exception_is_caught(self, client):
        """Exceptions in the on_event callback should not propagate."""
        client._on_event = lambda msg: (_ for _ in ()).throw(ValueError("oops"))
        # Should not raise
        client._handle_message({'type': 'pong'})

    def test_on_event_none_is_safe(self, client):
        """No callback registered should not raise."""
        assert client._on_event is None
        client._handle_message({'type': 'pong'})

    # -- lifecycle / properties -----------------------------------------------

    def test_connect_starts_daemon_thread(self, client):
        """connect() should start a daemon thread named 'ws-control'."""
        with patch('threading.Thread') as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread.is_alive.return_value = False
            mock_thread_cls.return_value = mock_thread
            client.connect()
        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()
        _, kwargs = mock_thread_cls.call_args
        assert kwargs.get('daemon') is True
        assert kwargs.get('name') == 'ws-control'

    def test_connect_is_idempotent(self, client):
        """A second connect() call while thread is alive should be a no-op."""
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        client._thread = mock_thread
        client.connect()
        mock_thread.start.assert_not_called()

    def test_is_connected_property(self, client):
        """is_connected property reflects _connected state."""
        assert client.is_connected is False
        client._connected = True
        assert client.is_connected is True

    def test_obs_client_count_property(self, client):
        """obs_client_count property reflects _obs_client_count."""
        assert client.obs_client_count == 0
        client._obs_client_count = 7
        assert client.obs_client_count == 7


# ---------------------------------------------------------------------------
# 3. button_style.py – icon/logo rendering (lines 82-104)
# ---------------------------------------------------------------------------

class TestButtonStyleIconRendering:
    """Tests for the team-logo / show-icon branch in update_button_style."""

    Cat = AppStorage.Category

    def _settings(self, overrides=None):
        """Return a local_settings dict with safe defaults."""
        Cat = AppStorage.Category
        defaults = {
            Cat.BUTTONS_FOLLOW_TEAM_COLORS: False,
            Cat.TEAM_1_BUTTON_COLOR: '#112233',
            Cat.TEAM_1_BUTTON_TEXT_COLOR: '#FFFFFF',
            Cat.TEAM_2_BUTTON_COLOR: '#334455',
            Cat.TEAM_2_BUTTON_TEXT_COLOR: '#FFFFFF',
            Cat.SELECTED_FONT: 'Default',
            Cat.BUTTONS_SHOW_ICON: False,
            Cat.BUTTONS_ICON_OPACITY: 0.3,
        }
        if overrides:
            defaults.update(overrides)
        return defaults

    def _cs(self, logo_url=None, color='#FF0000', text_color='#FFFFFF'):
        cs = MagicMock()
        cs.get_team_logo.return_value = logo_url
        cs.get_team_color.return_value = color
        cs.get_team_text_color.return_value = text_color
        return cs

    def test_icon_disabled_produces_no_background_image(self):
        """With BUTTONS_SHOW_ICON=False, style must not contain background-image."""
        btn_a, btn_b = MagicMock(), MagicMock()
        update_button_style(btn_a, btn_b, None, None, 100, 20, self._cs('https://x.com/logo.png'),
                            local_settings=self._settings())
        style = btn_a.style.call_args[1]['replace']
        assert 'background-image' not in style

    def test_icon_enabled_with_logo_adds_background_image(self):
        """With show_icon=True and a logo URL, background-image should appear."""
        Cat = AppStorage.Category
        btn_a, btn_b = MagicMock(), MagicMock()
        update_button_style(btn_a, btn_b, None, None, 100, 20,
                            self._cs('https://x.com/logo.png'),
                            local_settings=self._settings({Cat.BUTTONS_SHOW_ICON: True}))
        style = btn_a.style.call_args[1]['replace']
        assert 'background-image' in style

    def test_icon_enabled_without_logo_no_background_image(self):
        """With show_icon=True but no logo URL, background-image should not appear."""
        Cat = AppStorage.Category
        btn_a, btn_b = MagicMock(), MagicMock()
        update_button_style(btn_a, btn_b, None, None, 100, 20,
                            self._cs(logo_url=None),
                            local_settings=self._settings({Cat.BUTTONS_SHOW_ICON: True}))
        style = btn_a.style.call_args[1]['replace']
        assert 'background-image' not in style

    def test_icon_with_valid_hex_color_uses_rgba_overlay(self):
        """A valid #RRGGBB color should produce a linear-gradient rgba overlay."""
        Cat = AppStorage.Category
        btn_a, btn_b = MagicMock(), MagicMock()
        update_button_style(btn_a, btn_b, None, None, 100, 20,
                            self._cs('https://x.com/logo.png'),
                            local_settings=self._settings({
                                Cat.BUTTONS_SHOW_ICON: True,
                                Cat.TEAM_1_BUTTON_COLOR: '#FF0000',
                            }))
        style = btn_a.style.call_args[1]['replace']
        assert 'linear-gradient' in style
        assert 'rgba(255, 0, 0,' in style

    def test_icon_with_invalid_color_falls_back_to_plain_url(self):
        """An invalid hex color should produce url() with background-blend-mode."""
        Cat = AppStorage.Category
        btn_a, btn_b = MagicMock(), MagicMock()
        update_button_style(btn_a, btn_b, None, None, 100, 20,
                            self._cs('https://x.com/logo.png'),
                            local_settings=self._settings({
                                Cat.BUTTONS_SHOW_ICON: True,
                                Cat.TEAM_1_BUTTON_COLOR: 'red',  # not a #RRGGBB hex
                            }))
        style = btn_a.style.call_args[1]['replace']
        assert 'background-blend-mode: overlay' in style
        assert 'linear-gradient' not in style

    def test_follow_team_colors_uses_customize_state(self):
        """BUTTONS_FOLLOW_TEAM_COLORS=True should source colors from customize_state."""
        Cat = AppStorage.Category
        btn_a, btn_b = MagicMock(), MagicMock()
        cs = self._cs(color='#AABBCC')
        update_button_style(btn_a, btn_b, None, None, 100, 20, cs,
                            local_settings=self._settings({
                                Cat.BUTTONS_FOLLOW_TEAM_COLORS: True,
                            }))
        cs.get_team_color.assert_called()

    def test_none_buttons_are_skipped_gracefully(self):
        """Passing None for all buttons should not raise."""
        update_button_style(None, None, None, None, 100, 20, self._cs(),
                            local_settings=self._settings())

    def test_font_scale_adjusts_set_button_font_size(self):
        """A font with scale != 1.0 should resize the set button text."""
        Cat = AppStorage.Category
        btn_a, btn_b, set_a, set_b = MagicMock(), MagicMock(), MagicMock(), MagicMock()
        # 'Digital Dismay' has scale=1.16
        update_button_style(btn_a, btn_b, set_a, set_b, 100, 20, self._cs(),
                            local_settings=self._settings({
                                Cat.SELECTED_FONT: 'Digital Dismay',
                            }))
        set_style = set_a.style.call_args[1]['replace']
        expected_size = 24 * 1.16
        assert f'font-size: {expected_size}px' in set_style

    def test_font_offset_y_adds_padding_to_set_buttons(self):
        """A font with offset_y != 0 should produce padding styles on set buttons."""
        Cat = AppStorage.Category
        btn_a, btn_b, set_a, set_b = MagicMock(), MagicMock(), MagicMock(), MagicMock()
        # 'Aluminum' has offset_y=0.02
        update_button_style(btn_a, btn_b, set_a, set_b, 100, 20, self._cs(),
                            local_settings=self._settings({
                                Cat.SELECTED_FONT: 'Aluminum',
                            }))
        set_style = set_a.style.call_args[1]['replace']
        assert 'padding' in set_style

    def test_button_size_applied_to_style(self):
        """A non-zero button_size should add width/height to the style."""
        btn_a, btn_b = MagicMock(), MagicMock()
        update_button_style(btn_a, btn_b, None, None, 120, 20, self._cs(),
                            local_settings=self._settings())
        style = btn_a.style.call_args[1]['replace']
        assert 'width: 120px' in style
        assert 'height: 120px' in style

    def test_text_size_applied_to_style(self):
        """A non-zero button_text_size should add font-size to the style."""
        btn_a, btn_b = MagicMock(), MagicMock()
        update_button_style(btn_a, btn_b, None, None, 100, 24, self._cs(),
                            local_settings=self._settings())
        style = btn_a.style.call_args[1]['replace']
        assert 'font-size: 24.0px' in style


# ---------------------------------------------------------------------------
# 4. PasswordAuthenticator (authentication.py)
# ---------------------------------------------------------------------------

class TestPasswordAuthenticator:
    """Tests for check_user and compose_output in authentication.py."""

    def test_check_user_saves_oid_and_authenticated_on_success(self, monkeypatch):
        """Successful login should save CONFIGURED_OID and AUTHENTICATED=True."""
        users = {
            'alice': {'password': 'secret', 'control': 'my_oid', 'output': 'abc123'}
        }
        monkeypatch.setenv('SCOREBOARD_USERS', json.dumps(users))
        from app.authentication import PasswordAuthenticator
        result = PasswordAuthenticator.check_user('alice', 'secret')
        assert result is True
        assert AppStorage.load(AppStorage.Category.CONFIGURED_OID) == 'my_oid'
        assert AppStorage.load(AppStorage.Category.AUTHENTICATED) is True

    def test_check_user_returns_false_for_wrong_password(self, monkeypatch):
        """Wrong password should return False."""
        monkeypatch.setenv('SCOREBOARD_USERS',
                           json.dumps({'alice': {'password': 'secret'}}))
        from app.authentication import PasswordAuthenticator
        assert PasswordAuthenticator.check_user('alice', 'wrong') is False

    def test_check_user_returns_false_for_unknown_user(self, monkeypatch):
        """Unknown username should return False."""
        monkeypatch.setenv('SCOREBOARD_USERS',
                           json.dumps({'alice': {'password': 'secret'}}))
        from app.authentication import PasswordAuthenticator
        assert PasswordAuthenticator.check_user('bob', 'secret') is False

    def test_check_user_returns_false_when_env_not_set(self, monkeypatch):
        """check_user() should return False when SCOREBOARD_USERS is absent."""
        monkeypatch.delenv('SCOREBOARD_USERS', raising=False)
        from app.authentication import PasswordAuthenticator
        assert PasswordAuthenticator.check_user('alice', 'secret') is False

    def test_check_user_without_control_skips_oid_save(self, monkeypatch):
        """A user config without 'control' should not set CONFIGURED_OID."""
        users = {'alice': {'password': 'secret', 'output': 'abc123'}}
        monkeypatch.setenv('SCOREBOARD_USERS', json.dumps(users))
        from app.authentication import PasswordAuthenticator
        PasswordAuthenticator.check_user('alice', 'secret')
        assert AppStorage.load(AppStorage.Category.CONFIGURED_OID) is None

    def test_compose_output_prepends_base_url(self):
        """compose_output() should prepend the UNO base URL when missing."""
        from app.authentication import PasswordAuthenticator
        result = PasswordAuthenticator.compose_output('abc123')
        assert result == PasswordAuthenticator.UNO_OUTPUT_BASE_URL + 'abc123'

    def test_compose_output_leaves_full_url_unchanged(self):
        """compose_output() should not double-prepend a full URL."""
        from app.authentication import PasswordAuthenticator
        full_url = PasswordAuthenticator.UNO_OUTPUT_BASE_URL + 'abc123'
        assert PasswordAuthenticator.compose_output(full_url) == full_url

    def test_do_authenticate_users_false_when_env_not_set(self, monkeypatch):
        """do_authenticate_users() should return False when env var is absent."""
        monkeypatch.delenv('SCOREBOARD_USERS', raising=False)
        from app.authentication import PasswordAuthenticator
        assert PasswordAuthenticator.do_authenticate_users() is False

    def test_do_authenticate_users_true_when_env_set(self, monkeypatch):
        """do_authenticate_users() should return True when SCOREBOARD_USERS is set."""
        monkeypatch.setenv('SCOREBOARD_USERS', json.dumps({'alice': {'password': 'x'}}))
        from app.authentication import PasswordAuthenticator
        assert PasswordAuthenticator.do_authenticate_users() is True


# ---------------------------------------------------------------------------
# 5. AppStorage – refresh_state and OID-namespaced save/load
# ---------------------------------------------------------------------------

class TestAppStorageRefreshState:
    """Tests for AppStorage.refresh_state and OID-namespaced operations."""

    def test_save_with_oid_creates_nested_dict(self):
        """save() with an OID should store data under that OID."""
        Cat = AppStorage.Category
        AppStorage.save(Cat.USERNAME, 'testuser', oid='overlay1')
        assert AppStorage.load(Cat.USERNAME, oid='overlay1') == 'testuser'

    def test_save_with_oid_does_not_pollute_global_storage(self):
        """save() with an OID should not affect the top-level key."""
        Cat = AppStorage.Category
        AppStorage.save(Cat.USERNAME, 'nested', oid='overlay1')
        assert AppStorage.load(Cat.USERNAME) is None

    def test_load_missing_oid_key_returns_default(self):
        """load() for a missing OID key should return the default."""
        Cat = AppStorage.Category
        result = AppStorage.load(Cat.USERNAME, default='fallback', oid='nonexistent')
        assert result == 'fallback'

    def test_refresh_state_clears_oid_storage(self):
        """refresh_state() without preserve_keys should remove all data for the OID."""
        Cat = AppStorage.Category
        AppStorage.save(Cat.USERNAME, 'alice', oid='overlay1')
        AppStorage.refresh_state('overlay1')
        assert AppStorage.load(Cat.USERNAME, oid='overlay1') is None

    def test_refresh_state_with_preserve_keys_retains_specified_keys(self):
        """refresh_state() with preserve_keys should keep only those keys."""
        Cat = AppStorage.Category
        AppStorage.save(Cat.USERNAME, 'alice', oid='overlay2')
        AppStorage.save(Cat.AUTHENTICATED, True, oid='overlay2')
        AppStorage.refresh_state('overlay2', preserve_keys=[Cat.USERNAME])
        assert AppStorage.load(Cat.USERNAME, oid='overlay2') == 'alice'
        assert AppStorage.load(Cat.AUTHENTICATED, oid='overlay2') is None

    def test_refresh_state_for_unknown_oid_is_noop(self):
        """refresh_state() on a non-existent OID should not raise."""
        AppStorage.refresh_state('nonexistent_oid')  # must not raise
