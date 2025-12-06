/**
 * Underdog Fantasy Draft Sounds - Content Script
 *
 * This script monitors the Underdog Fantasy draft page for events and
 * sends messages to the background script to play appropriate sounds.
 */

(function() {
  'use strict';

  // State tracking
  let state = {
    isEnabled: true,
    currentPick: null,
    isMyTurn: false,
    lobbyPlayerCount: 0,
    lastPickPlayer: null,
    draftStarted: false,
    initialized: false,
    username: null
  };

  // Default settings
  let settings = {
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

  // Sound types
  const SOUND_TYPES = {
    MY_TURN: 'myTurn',
    OTHER_PICK: 'otherPick',
    PLAYER_JOIN: 'playerJoin',
    PLAYER_LEAVE: 'playerLeave',
    DRAFT_START: 'draftStart'
  };

  /**
   * Initialize the extension
   */
  async function init() {
    if (state.initialized) return;

    console.log('[Underdog Draft Sounds] Initializing...');

    // Load settings from storage
    await loadSettings();

    // Try to detect the user's username
    detectUsername();

    // Start observing the page
    startObserver();

    // Initial page scan
    scanPage();

    // Listen for messages from popup/background
    browser.runtime.onMessage.addListener(handleMessage);

    state.initialized = true;
    console.log('[Underdog Draft Sounds] Initialized successfully');
  }

  /**
   * Load settings from browser storage
   */
  async function loadSettings() {
    try {
      const stored = await browser.storage.local.get('settings');
      if (stored.settings) {
        settings = { ...settings, ...stored.settings };
      }
    } catch (e) {
      console.error('[Underdog Draft Sounds] Error loading settings:', e);
    }
  }

  /**
   * Handle messages from popup or background script
   */
  function handleMessage(message, sender, sendResponse) {
    switch (message.type) {
      case 'UPDATE_SETTINGS':
        settings = { ...settings, ...message.settings };
        sendResponse({ success: true });
        break;
      case 'GET_STATE':
        sendResponse({ state, settings });
        break;
      case 'TEST_SOUND':
        playSound(message.soundType);
        sendResponse({ success: true });
        break;
    }
    return true;
  }

  /**
   * Try to detect the user's username from the page
   */
  function detectUsername() {
    // Common selectors where username might appear
    const usernameSelectors = [
      '[data-testid="user-menu"] span',
      '.user-name',
      '.username',
      '.profile-name',
      '[class*="UserName"]',
      '[class*="userName"]',
      '[class*="user-name"]'
    ];

    for (const selector of usernameSelectors) {
      const element = document.querySelector(selector);
      if (element && element.textContent.trim()) {
        state.username = element.textContent.trim();
        console.log('[Underdog Draft Sounds] Detected username:', state.username);
        return;
      }
    }
  }

  /**
   * Start the MutationObserver to watch for page changes
   */
  function startObserver() {
    const observer = new MutationObserver((mutations) => {
      // Debounce rapid changes
      if (observer.timeout) {
        clearTimeout(observer.timeout);
      }
      observer.timeout = setTimeout(() => {
        handleMutations(mutations);
      }, 100);
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ['class', 'data-testid', 'aria-label']
    });

    console.log('[Underdog Draft Sounds] Observer started');
  }

  /**
   * Handle DOM mutations
   */
  function handleMutations(mutations) {
    if (!settings.enabled) return;

    // Check for draft-related changes
    scanPage();
  }

  /**
   * Scan the page for draft state changes
   */
  function scanPage() {
    // Check if we're on a draft page
    const isDraftPage = checkIfDraftPage();
    if (!isDraftPage) return;

    // Check for lobby (pre-draft)
    if (checkLobbyState()) return;

    // Check draft state
    checkDraftState();
  }

  /**
   * Check if we're on a draft-related page
   */
  function checkIfDraftPage() {
    const url = window.location.href.toLowerCase();
    return url.includes('draft') ||
           url.includes('lobby') ||
           document.querySelector('[class*="draft"]') !== null ||
           document.querySelector('[class*="Draft"]') !== null;
  }

  /**
   * Check and handle lobby state (pre-draft waiting room)
   */
  function checkLobbyState() {
    // Look for lobby indicators
    const lobbySelectors = [
      '[class*="lobby"]',
      '[class*="Lobby"]',
      '[class*="waiting"]',
      '[class*="Waiting"]',
      '[data-testid*="lobby"]'
    ];

    let isLobby = false;
    for (const selector of lobbySelectors) {
      if (document.querySelector(selector)) {
        isLobby = true;
        break;
      }
    }

    if (!isLobby) return false;

    // Count players in lobby
    const playerSelectors = [
      '[class*="participant"]',
      '[class*="Participant"]',
      '[class*="player-card"]',
      '[class*="PlayerCard"]',
      '[class*="user-entry"]',
      '[class*="UserEntry"]',
      '[class*="draft-entry"]',
      '[class*="entrant"]',
      '[class*="Entrant"]'
    ];

    let playerCount = 0;
    for (const selector of playerSelectors) {
      const elements = document.querySelectorAll(selector);
      if (elements.length > 0) {
        playerCount = elements.length;
        break;
      }
    }

    // Also try counting by looking for avatar/profile elements in lobby area
    if (playerCount === 0) {
      const avatarSelectors = [
        '[class*="avatar"]',
        '[class*="Avatar"]',
        '[class*="profile-pic"]'
      ];

      for (const selector of avatarSelectors) {
        const elements = document.querySelectorAll(selector);
        if (elements.length > 1) { // More than 1 suggests multiple players
          playerCount = elements.length;
          break;
        }
      }
    }

    // Check for player count changes
    if (state.lobbyPlayerCount > 0) {
      if (playerCount > state.lobbyPlayerCount && settings.sounds.playerJoin) {
        console.log('[Underdog Draft Sounds] Player joined lobby');
        playSound(SOUND_TYPES.PLAYER_JOIN);
      } else if (playerCount < state.lobbyPlayerCount && settings.sounds.playerLeave) {
        console.log('[Underdog Draft Sounds] Player left lobby');
        playSound(SOUND_TYPES.PLAYER_LEAVE);
      }
    }

    state.lobbyPlayerCount = playerCount;
    return true;
  }

  /**
   * Check and handle draft state
   */
  function checkDraftState() {
    // Check if draft just started
    const draftActiveSelectors = [
      '[class*="draft-board"]',
      '[class*="DraftBoard"]',
      '[class*="draft-active"]',
      '[class*="pick-clock"]',
      '[class*="PickClock"]',
      '[class*="draft-timer"]',
      '[class*="DraftTimer"]'
    ];

    let draftActive = false;
    for (const selector of draftActiveSelectors) {
      if (document.querySelector(selector)) {
        draftActive = true;
        break;
      }
    }

    if (draftActive && !state.draftStarted) {
      state.draftStarted = true;
      if (settings.sounds.draftStart) {
        console.log('[Underdog Draft Sounds] Draft started!');
        playSound(SOUND_TYPES.DRAFT_START);
      }
    }

    // Check current pick / whose turn
    checkCurrentPick();

    // Check for new picks made
    checkForNewPicks();
  }

  /**
   * Check whose turn it is to pick
   */
  function checkCurrentPick() {
    // Look for indicators that it's user's turn
    const myTurnIndicators = [
      '[class*="your-turn"]',
      '[class*="YourTurn"]',
      '[class*="my-turn"]',
      '[class*="MyTurn"]',
      '[class*="current-pick"][class*="self"]',
      '[class*="active-picker"][class*="self"]',
      '[class*="on-the-clock"]',
      '[class*="OnTheClock"]'
    ];

    let isMyTurn = false;

    // Check explicit "your turn" indicators
    for (const selector of myTurnIndicators) {
      const element = document.querySelector(selector);
      if (element) {
        isMyTurn = true;
        break;
      }
    }

    // Also check if current picker name matches our username
    if (!isMyTurn && state.username) {
      const currentPickerSelectors = [
        '[class*="current-picker"]',
        '[class*="CurrentPicker"]',
        '[class*="active-drafter"]',
        '[class*="on-clock"] [class*="name"]'
      ];

      for (const selector of currentPickerSelectors) {
        const element = document.querySelector(selector);
        if (element && element.textContent.toLowerCase().includes(state.username.toLowerCase())) {
          isMyTurn = true;
          break;
        }
      }
    }

    // Check for text content indicating your turn
    const pageText = document.body.innerText.toLowerCase();
    if (pageText.includes("you're on the clock") ||
        pageText.includes("your pick") ||
        pageText.includes("your turn") ||
        pageText.includes("make your selection")) {
      isMyTurn = true;
    }

    // Play sound if turn just changed to user
    if (isMyTurn && !state.isMyTurn && settings.sounds.myTurn) {
      console.log('[Underdog Draft Sounds] It\'s your turn!');
      playSound(SOUND_TYPES.MY_TURN);
    }

    state.isMyTurn = isMyTurn;
  }

  /**
   * Check for new picks being made
   */
  function checkForNewPicks() {
    // Look for pick history or recent picks
    const pickSelectors = [
      '[class*="pick-history"] [class*="pick-item"]',
      '[class*="PickHistory"] [class*="PickItem"]',
      '[class*="draft-log"] [class*="entry"]',
      '[class*="DraftLog"] [class*="Entry"]',
      '[class*="recent-pick"]',
      '[class*="RecentPick"]',
      '[class*="last-pick"]',
      '[class*="LastPick"]',
      '[class*="pick-made"]'
    ];

    let latestPick = null;

    for (const selector of pickSelectors) {
      const elements = document.querySelectorAll(selector);
      if (elements.length > 0) {
        // Get the most recent pick (usually first or last depending on sort)
        const lastElement = elements[elements.length - 1];
        latestPick = lastElement.textContent.trim();
        break;
      }
    }

    // Also check for pick number changes
    const pickNumberSelectors = [
      '[class*="pick-number"]',
      '[class*="PickNumber"]',
      '[class*="current-pick"]',
      '[class*="CurrentPick"]',
      '[class*="round-pick"]'
    ];

    for (const selector of pickNumberSelectors) {
      const element = document.querySelector(selector);
      if (element) {
        const pickNum = element.textContent.match(/\d+/);
        if (pickNum) {
          const newPickNumber = parseInt(pickNum[0], 10);
          if (state.currentPick !== null && newPickNumber !== state.currentPick) {
            latestPick = `Pick ${newPickNumber}`;
          }
          state.currentPick = newPickNumber;
        }
        break;
      }
    }

    // If we detected a new pick that's different from the last one
    if (latestPick && latestPick !== state.lastPickPlayer) {
      // Only play sound if it's not our turn (we made the pick)
      if (!state.isMyTurn && settings.sounds.otherPick) {
        console.log('[Underdog Draft Sounds] New pick detected:', latestPick);
        playSound(SOUND_TYPES.OTHER_PICK);
      }
      state.lastPickPlayer = latestPick;
    }
  }

  /**
   * Send message to background script to play a sound
   */
  function playSound(soundType) {
    if (!settings.enabled) return;

    browser.runtime.sendMessage({
      type: 'PLAY_SOUND',
      soundType: soundType,
      volume: settings.volume
    }).catch(err => {
      console.error('[Underdog Draft Sounds] Error playing sound:', err);
    });
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Also re-initialize on URL changes (SPA navigation)
  let lastUrl = location.href;
  new MutationObserver(() => {
    const url = location.href;
    if (url !== lastUrl) {
      lastUrl = url;
      state.initialized = false;
      init();
    }
  }).observe(document, { subtree: true, childList: true });

})();
