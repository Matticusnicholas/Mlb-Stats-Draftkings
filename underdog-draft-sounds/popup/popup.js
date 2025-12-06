/**
 * Underdog Fantasy Draft Sounds - Popup Script
 *
 * Handles the settings UI for the extension.
 */

document.addEventListener('DOMContentLoaded', async () => {
  // Elements
  const enabledCheckbox = document.getElementById('enabled');
  const volumeSlider = document.getElementById('volume');
  const volumeDisplay = document.getElementById('volume-display');
  const statusText = document.getElementById('status');
  const soundToggles = document.querySelectorAll('.sound-option input[type="checkbox"]');
  const testButtons = document.querySelectorAll('.test-btn');

  // Load current settings
  let settings = await loadSettings();
  applySettingsToUI(settings);

  // Master enable/disable toggle
  enabledCheckbox.addEventListener('change', async () => {
    settings.enabled = enabledCheckbox.checked;
    await saveSettings(settings);
    updateUIState(settings.enabled);
    updateStatus(settings.enabled ? 'Enabled' : 'Disabled');
  });

  // Volume slider
  volumeSlider.addEventListener('input', () => {
    const volume = volumeSlider.value;
    volumeDisplay.textContent = `${volume}%`;
  });

  volumeSlider.addEventListener('change', async () => {
    settings.volume = volumeSlider.value / 100;
    await saveSettings(settings);
    updateStatus('Volume saved');
  });

  // Individual sound toggles
  soundToggles.forEach(toggle => {
    toggle.addEventListener('change', async () => {
      const soundType = toggle.dataset.sound;
      settings.sounds[soundType] = toggle.checked;
      await saveSettings(settings);
      updateStatus(`${formatSoundName(soundType)} ${toggle.checked ? 'enabled' : 'disabled'}`);
    });
  });

  // Test buttons
  testButtons.forEach(button => {
    button.addEventListener('click', async () => {
      const soundType = button.dataset.sound;
      try {
        await browser.runtime.sendMessage({
          type: 'TEST_SOUND',
          soundType: soundType,
          volume: settings.volume
        });
        updateStatus(`Playing ${formatSoundName(soundType)}`);
      } catch (error) {
        console.error('Error testing sound:', error);
        updateStatus('Error playing sound', true);
      }
    });
  });

  /**
   * Load settings from storage
   */
  async function loadSettings() {
    const defaults = {
      enabled: true,
      volume: 0.7,
      sounds: {
        myTurn: true,
        otherPick: true,
        playerJoin: true,
        playerLeave: true,
        draftStart: true
      }
    };

    try {
      const stored = await browser.storage.local.get('settings');
      return { ...defaults, ...stored.settings };
    } catch (error) {
      console.error('Error loading settings:', error);
      return defaults;
    }
  }

  /**
   * Save settings to storage
   */
  async function saveSettings(settings) {
    try {
      await browser.storage.local.set({ settings });
      // Notify content scripts of settings change
      const tabs = await browser.tabs.query({
        url: ['*://underdogfantasy.com/*', '*://www.underdogfantasy.com/*']
      });
      for (const tab of tabs) {
        try {
          await browser.tabs.sendMessage(tab.id, {
            type: 'UPDATE_SETTINGS',
            settings: settings
          });
        } catch (e) {
          // Tab might not have content script loaded
        }
      }
    } catch (error) {
      console.error('Error saving settings:', error);
    }
  }

  /**
   * Apply settings to UI elements
   */
  function applySettingsToUI(settings) {
    enabledCheckbox.checked = settings.enabled;
    volumeSlider.value = Math.round(settings.volume * 100);
    volumeDisplay.textContent = `${Math.round(settings.volume * 100)}%`;

    soundToggles.forEach(toggle => {
      const soundType = toggle.dataset.sound;
      toggle.checked = settings.sounds[soundType] !== false;
    });

    updateUIState(settings.enabled);
  }

  /**
   * Update UI enabled/disabled state
   */
  function updateUIState(enabled) {
    document.body.classList.toggle('disabled', !enabled);
  }

  /**
   * Update status text
   */
  function updateStatus(message, isError = false) {
    statusText.textContent = message;
    statusText.classList.remove('active', 'error');
    statusText.classList.add(isError ? 'error' : 'active');

    // Reset after a few seconds
    setTimeout(() => {
      statusText.textContent = settings.enabled ? 'Ready' : 'Disabled';
      statusText.classList.remove('active', 'error');
    }, 2000);
  }

  /**
   * Format sound type name for display
   */
  function formatSoundName(soundType) {
    const names = {
      myTurn: 'Your Turn',
      otherPick: 'Other Picks',
      playerJoin: 'Player Join',
      playerLeave: 'Player Leave',
      draftStart: 'Draft Start'
    };
    return names[soundType] || soundType;
  }

  // Initial status
  updateStatus(settings.enabled ? 'Ready' : 'Disabled');
});
