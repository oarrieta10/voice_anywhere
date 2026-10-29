# Voice Anywhere

Offline dictation for any Windows program. Press **Ctrl+Alt+Space**, speak, press it again,
and the text appears where your cursor is. Press **Esc** while recording to cancel.

Speech is turned into text on this laptop by faster-whisper (an offline version of OpenAI's
Whisper speech-recognition model). **Nothing is sent to the internet**: there is no network
call at all, the recording is only kept in memory and is thrown away after each dictation,
and the log never contains what you said.

## Everyday use

1. Click where you want the text (an Outlook email, a Teams chat, a Word document, a browser box...).
2. Press **Ctrl+Alt+Space** (or your own hotkey, see Settings). A small black pill fades in at
   the bottom-right corner of the screen, above the clock. Its white bars move with your voice,
   so you can see the microphone is hearing you.
3. Speak normally. Punctuation is added for you.
4. Press the hotkey again. The pill shrinks to a row of dots with a soft wave running across
   them while your speech is turned into text (a second or two), then fades away as the text
   is typed in at your cursor.

The pill never takes the cursor away from the program you are typing in, and mouse clicks go
straight through it.

- **Esc** while the bars show: cancel, nothing is typed.
- If you click into another window while speaking, the text still goes to the window you
  started in.
- One recording can last up to 2 minutes; after that it stops by itself and types what it heard.
- If it heard nothing, the dots simply fade away and nothing is typed.
- The text is tidied before it is typed (all on this laptop, no AI):
  - filler sounds go: "I think, um, we should" becomes "I think we should"
    (English um, uh, uhm, er, erm, hmm; Spanish eh, em, mmm). Real words that are sometimes
    used as fillers ("este", "o sea", "pues", "like") are left alone;
  - a word said twice by accident is kept once: "the the report" becomes "the report".
    Words often doubled on purpose stay ("that that", "had had", "no no", "sí sí", "ya ya");
  - stray spaces and leftover commas are removed, and a sentence that started with a filler
    gets its capital letter back.
  To switch this off, see `VOICE_CLEANUP` under Settings.
- Your clipboard is left as it was: the app borrows it for a moment to paste, then puts your
  previous contents back. The dictated text is also kept out of Windows clipboard history (Win+V).

### The tray icon

A round microphone icon sits by the clock (it may be hidden under the **^** arrow; you can drag
it next to the clock to keep it visible).

| Colour | Meaning |
|---|---|
| Blue | Ready (hover over it to check the speech model has finished loading) |
| Red | Listening |
| Amber | Transcribing |

Right-click it to see the current status or to **Quit**.

The speech model takes a few seconds to load after the app starts. If you dictate before it is
ready, the first dictation simply takes a little longer.

## Setup (once)

You need Python 3.12 (already installed on this laptop) and the Whisper `small` model in the local
Hugging Face cache (already there, from Kuadrant). The app never downloads anything.

Open PowerShell in this folder (`C:\Tool Dev\voice-anywhere`) and run:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then **double-click `create_shortcut.bat`**. It:

- puts a "Voice Anywhere" shortcut in your Startup folder, so the app starts every time you sign in, and
- starts it right away.

No administrator rights are needed, and it is safe to run again.

To stop it starting with Windows, double-click **`remove_shortcut.bat`** (then right-click the tray
icon and choose Quit to stop the copy that is running).

To start it by hand without the shortcut:

```powershell
.venv\Scripts\pythonw.exe -m voice_anywhere
```

Starting it a second time does nothing: only one copy ever runs.

## Settings

Settings are Windows environment variables. To change one, run a `setx` line in PowerShell, then
quit Voice Anywhere from the tray and start it again (or sign out and back in).

| Variable | What it does | Default |
|---|---|---|
| `VOICE_HOTKEY` | The start/stop key, for example `ctrl+shift+d` or `win+alt+f9` | `ctrl+alt+space` |
| `VOICE_WHISPER_LANG` | Language you speak, as a two-letter code (`en`, `es`, ...); a list such as `en,es` to detect which of those you are speaking; or `auto` to detect any language | `en` |
| `VOICE_WHISPER_MODEL` | Model size (`small` or `base`), or a folder containing a model | `small` |
| `VOICE_CLEANUP` | Tidy the text before typing it (`on`), or type exactly what Whisper wrote (`off`) | `on` |

Examples:

```powershell
setx VOICE_HOTKEY "ctrl+shift+d"
```

```powershell
setx VOICE_WHISPER_LANG "es"
```

**Dictating in English and Spanish:** `setx VOICE_WHISPER_LANG "en,es"` makes each dictation
come out in whichever of the two you spoke. Choosing from just those two is more reliable than
`auto`, which can mistake Spanish for Portuguese, Galician or Catalan. The language check adds
about one second to each dictation; a single fixed language (`en` or `es`) is the quickest.
Very short dictations (one or two words) are the hardest to tell apart.

`base` is faster but makes more mistakes than `small`. To go back to a default, remove the variable
under *Settings > System > About > Advanced system settings > Environment Variables*.

A hotkey is one key, optionally with `ctrl`, `alt`, `shift` or `win` in front: a letter, a digit,
`f1`-`f24`, `space`, `enter`, `tab`, `insert`, `delete`, `home`, `end`, `pageup`, `pagedown`,
`pause` or an arrow (`up`, `down`, `left`, `right`).

A function key (`f1`-`f24`), `pause` or `insert` can be used on its own, for example
`setx VOICE_HOTKEY "f9"`. That key then belongs to Voice Anywhere in every program. Any
other key needs at least one of `ctrl`, `alt`, `shift` or `win`, so that ordinary typing
keys such as Tab or Space keep working.

## If something goes wrong

- **A message says the hotkey could not be registered.** Another program already uses that key
  combination. Pick another one with `VOICE_HOTKEY` (see Settings).
- **Nothing is heard, or "Could not open the microphone".** Check *Settings > Privacy & security >
  Microphone*: "Microphone access" and "Let desktop apps access your microphone" must be on. The app
  uses the default microphone (*Settings > System > Sound > Input*).
- **The pill shows but no text appears in one particular program.** Windows does not let normal
  programs type into programs that run *as administrator*. Dictate into a normal window instead,
  or start Voice Anywhere as administrator too.
- **Text appears in the wrong place.** The text goes into the window that had focus when you pressed
  the hotkey the first time. Click into the right box before you start.
- **"Could not load Whisper model".** The model is not in the local cache. Set `VOICE_WHISPER_MODEL`
  to a model that is (`small` or `base`).

The log is in `%LOCALAPPDATA%\voice-anywhere\voice-anywhere.log` (paste that into the File
Explorer address bar). It only records start-up, timings and lengths, never what you said.

## For development

Run with a console (Ctrl+C or Quit in the tray to stop):

```powershell
.venv\Scripts\python.exe -m voice_anywhere
```

Run the tests (they use fakes: no microphone, hotkey, clipboard or Whisper model is touched):

```powershell
.venv\Scripts\python.exe -m pip install pytest
```

```powershell
.venv\Scripts\python.exe -m pytest -q
```

How the code is laid out (`voice_anywhere\`):

| File | Job |
|---|---|
| `__main__.py` | Start-up: log file, single-instance check, error message boxes |
| `app.py` | The controller: hotkey -> record -> transcribe -> paste |
| `hotkey.py` | The global hotkey and Esc, through the Windows `RegisterHotKey` function |
| `recorder.py` | Microphone recording into memory (16 kHz mono), with the 2-minute limit |
| `transcriber.py` | faster-whisper speech-to-text on the CPU |
| `cleanup.py` | Tidies the text: filler sounds, doubled words, spacing |
| `inserter.py` | Paste at the cursor: clipboard + Ctrl+V, then restore the clipboard |
| `tray.py` | The tray icon and its menu |
| `pill.py` | Draws the pill: sound bars while listening, a dot wave while transcribing |
| `overlay.py` | Shows the pill in a see-through, click-through window that never takes the focus |

`scripts\make_shortcut.ps1` makes the Startup shortcut; `scripts\make_icon.py` redraws
`voice-anywhere.ico` (`.venv\Scripts\python.exe -m scripts.make_icon`).
