# Underdog Fantasy Draft Sounds

A Firefox extension that adds sound notifications to Underdog Fantasy drafts. Never miss your pick again!

## Features

- **Your Turn Alert** - Attention-grabbing chime when it's your turn to pick
- **Other Picks** - Subtle notification when other players make picks
- **Lobby Notifications** - Sounds when players join or leave the pre-draft lobby
- **Draft Start Alert** - Fanfare when the draft begins
- **Volume Control** - Adjustable volume for all sounds
- **Individual Toggle** - Enable/disable each sound type separately
- **Test Sounds** - Preview each sound from the popup

## Installation

### Temporary Installation (for development/testing)

1. Open Firefox and navigate to `about:debugging`
2. Click "This Firefox" in the left sidebar
3. Click "Load Temporary Add-on..."
4. Navigate to the `underdog-draft-sounds` folder
5. Select the `manifest.json` file
6. The extension will now appear in your toolbar

### Permanent Installation

To install permanently, the extension needs to be signed by Mozilla:

1. Create a Mozilla Add-ons account at [addons.mozilla.org](https://addons.mozilla.org)
2. Package the extension as a `.zip` file
3. Submit it for signing (you can keep it unlisted if you prefer)
4. Download and install the signed `.xpi` file

## Usage

1. Click the extension icon in your Firefox toolbar to open settings
2. Toggle the master switch to enable/disable all sounds
3. Adjust the volume slider to your preference
4. Toggle individual sound types on/off
5. Click the play button next to each sound to preview it
6. Navigate to [underdogfantasy.com](https://underdogfantasy.com) and join a draft!

## How It Works

The extension uses a content script that monitors the Underdog Fantasy website for:

- **DOM changes** via MutationObserver
- **Pick indicators** - Detects when picks are made
- **Turn indicators** - Identifies when it's your turn
- **Lobby state** - Tracks player count changes

Sounds are generated using the Web Audio API, so no external audio files are required.

## Sound Types

| Sound | Trigger | Description |
|-------|---------|-------------|
| Your Turn | It's your pick | Ascending 4-note chime (C-E-G-C) |
| Other Pick | Someone else picks | Subtle single tone |
| Player Join | Player enters lobby | Friendly ascending two-note |
| Player Leave | Player exits lobby | Descending two-note |
| Draft Start | Draft begins | Triumphant fanfare |

## Troubleshooting

### Sounds not playing?

1. Make sure the extension is enabled (check the toggle in the popup)
2. Ensure browser audio is not muted
3. Check that individual sound types are enabled
4. Try clicking a test button in the popup to verify audio works

### Extension not detecting events?

The extension uses pattern matching to detect UI changes. If Underdog Fantasy updates their website significantly, the detection may need to be updated. Please open an issue if this happens.

### Browser autoplay policy?

Modern browsers restrict autoplay. The extension handles this by using the Web Audio API, but you may need to interact with the Underdog Fantasy page once before sounds will play.

## Development

### Project Structure

```
underdog-draft-sounds/
├── manifest.json      # Extension manifest
├── content.js         # Content script (monitors page)
├── background.js      # Background script (plays sounds)
├── icons/
│   └── icon.svg       # Extension icon
├── popup/
│   ├── popup.html     # Settings popup
│   ├── popup.css      # Popup styles
│   └── popup.js       # Popup logic
└── README.md
```

### Building for Distribution

1. Ensure all files are in place
2. Create a zip file containing all extension files:
   ```bash
   zip -r underdog-draft-sounds.zip manifest.json content.js background.js icons/ popup/
   ```
3. Submit to [addons.mozilla.org](https://addons.mozilla.org) for signing

## Contributing

Contributions are welcome! If you notice the extension isn't detecting events properly on the Underdog Fantasy site, please:

1. Open the browser console (F12 → Console)
2. Look for messages starting with `[Underdog Draft Sounds]`
3. Open an issue with the console output and describe what's not working

## License

MIT License - feel free to modify and distribute!

## Disclaimer

This extension is not affiliated with, endorsed by, or connected to Underdog Fantasy. It's an independent tool created to enhance the user experience.
