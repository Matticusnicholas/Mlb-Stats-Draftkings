/**
 * Underdog Fantasy Draft Sounds - Background Script
 *
 * Handles audio playback for draft events using Web Audio API.
 * Generates pleasant notification sounds programmatically.
 */

// Audio context for generating sounds
let audioContext = null;

/**
 * Initialize or get the audio context
 */
function getAudioContext() {
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
  }
  return audioContext;
}

/**
 * Sound definitions - each sound type has its own characteristics
 */
const SOUND_DEFINITIONS = {
  myTurn: {
    // Attention-grabbing ascending chime
    notes: [523.25, 659.25, 783.99, 1046.50], // C5, E5, G5, C6
    durations: [0.15, 0.15, 0.15, 0.3],
    type: 'sine',
    envelope: { attack: 0.01, decay: 0.1, sustain: 0.3, release: 0.2 }
  },
  otherPick: {
    // Subtle single tone
    notes: [440],
    durations: [0.2],
    type: 'sine',
    envelope: { attack: 0.01, decay: 0.05, sustain: 0.5, release: 0.15 }
  },
  playerJoin: {
    // Friendly ascending two-note
    notes: [392, 523.25], // G4, C5
    durations: [0.1, 0.2],
    type: 'sine',
    envelope: { attack: 0.01, decay: 0.05, sustain: 0.4, release: 0.15 }
  },
  playerLeave: {
    // Descending two-note
    notes: [523.25, 392], // C5, G4
    durations: [0.1, 0.2],
    type: 'sine',
    envelope: { attack: 0.01, decay: 0.05, sustain: 0.4, release: 0.15 }
  },
  draftStart: {
    // Triumphant fanfare
    notes: [523.25, 523.25, 523.25, 698.46, 783.99], // C5, C5, C5, F5, G5
    durations: [0.1, 0.1, 0.1, 0.2, 0.4],
    type: 'sine',
    envelope: { attack: 0.01, decay: 0.1, sustain: 0.5, release: 0.3 }
  }
};

/**
 * Play a synthesized sound
 */
function playSound(soundType, volume = 0.7) {
  const ctx = getAudioContext();
  const soundDef = SOUND_DEFINITIONS[soundType];

  if (!soundDef) {
    console.error('[Underdog Draft Sounds] Unknown sound type:', soundType);
    return;
  }

  // Resume audio context if suspended (browser autoplay policy)
  if (ctx.state === 'suspended') {
    ctx.resume();
  }

  let startTime = ctx.currentTime;

  soundDef.notes.forEach((freq, index) => {
    const duration = soundDef.durations[index];
    const { attack, decay, sustain, release } = soundDef.envelope;

    // Create oscillator
    const oscillator = ctx.createOscillator();
    oscillator.type = soundDef.type;
    oscillator.frequency.setValueAtTime(freq, startTime);

    // Create gain node for envelope
    const gainNode = ctx.createGain();

    // Create master volume
    const masterGain = ctx.createGain();
    masterGain.gain.setValueAtTime(volume, ctx.currentTime);

    // Connect nodes
    oscillator.connect(gainNode);
    gainNode.connect(masterGain);
    masterGain.connect(ctx.destination);

    // Apply ADSR envelope
    const noteStart = startTime;
    const noteEnd = startTime + duration;

    gainNode.gain.setValueAtTime(0, noteStart);
    gainNode.gain.linearRampToValueAtTime(1, noteStart + attack);
    gainNode.gain.linearRampToValueAtTime(sustain, noteStart + attack + decay);
    gainNode.gain.setValueAtTime(sustain, noteEnd - release);
    gainNode.gain.linearRampToValueAtTime(0, noteEnd);

    // Start and stop oscillator
    oscillator.start(noteStart);
    oscillator.stop(noteEnd + 0.1);

    // Update start time for next note
    startTime += duration;
  });
}

/**
 * Handle messages from content script
 */
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'PLAY_SOUND':
      try {
        playSound(message.soundType, message.volume || 0.7);
        sendResponse({ success: true });
      } catch (error) {
        console.error('[Underdog Draft Sounds] Error playing sound:', error);
        sendResponse({ success: false, error: error.message });
      }
      break;

    case 'TEST_SOUND':
      try {
        playSound(message.soundType, message.volume || 0.7);
        sendResponse({ success: true });
      } catch (error) {
        sendResponse({ success: false, error: error.message });
      }
      break;

    case 'GET_SOUND_TYPES':
      sendResponse({ soundTypes: Object.keys(SOUND_DEFINITIONS) });
      break;
  }
  return true;
});

/**
 * Initialize default settings on install
 */
browser.runtime.onInstalled.addListener(async (details) => {
  if (details.reason === 'install') {
    const defaultSettings = {
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

    await browser.storage.local.set({ settings: defaultSettings });
    console.log('[Underdog Draft Sounds] Extension installed with default settings');
  }
});

console.log('[Underdog Draft Sounds] Background script loaded');
