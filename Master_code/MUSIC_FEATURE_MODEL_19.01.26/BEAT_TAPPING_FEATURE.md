# Beat Tapping Feature

A manual beat synchronization system that allows real-time phase adjustment through keyboard tapping.

## Overview

This feature enables users to manually synchronize the motor's motion phase with the music by tapping the "P" key on their keyboard in rhythm with the beat. The system calculates the intended phase and applies a smooth 4-second transition to minimize jerky movement.

## Architecture

### Modules

1. **beat_tapper.py** - New module containing:
   - `BeatTapper` class: Captures and analyzes tap timing
   - `PhaseTransitioner` class: Manages smooth phase transitions

2. **web_interface.py** - Updated with:
   - Beat tapper and phase transitioner instances
   - API endpoints for tapping functionality
   - Integration with status update thread

3. **index.html** - Enhanced with:
   - Beat tapping UI panel
   - Keyboard event listener for 'P' key
   - Real-time tap count display

## How It Works

### 1. Tap Collection
- User presses 'P' key in rhythm with the music
- Each tap timestamp is recorded
- Minimum 3 taps required for calculation
- Maximum 32 taps stored (FIFO)

### 2. BPM Detection
- After 1.5 seconds of no tapping, processing begins
- Calculate intervals between taps
- Filter outliers using standard deviation
- Calculate average BPM from filtered intervals

### 3. Phase Calculation
- Determine phase offset needed to align beats with taps
- Uses the first tap as the reference point
- Calculates the phase difference from current motor phase

### 4. Smooth Transition
- 4-second gliding transition initiated
- Uses ease-in-out cubic easing for smoothness
- Continuously updates motor phase during transition
- Minimizes jerky movement

## Usage

### Web Interface

1. Start playing music (Connect → Select Song → Run)
2. Wait for music to start
3. Press **P** on your keyboard in rhythm with the beat
4. Tap at least 3 times (8-16 taps recommended for accuracy)
5. Wait 1.5 seconds after last tap
6. System automatically:
   - Detects the beat timing
   - Calculates required phase adjustment
   - Applies smooth 4-second transition
7. Watch for status messages:
   - "🎵 Beat detected: X BPM. Starting 4-second phase transition..."
   - "✅ Phase transition complete! Motion is now synchronized with your taps."

### UI Elements

**Beat Tapping Panel:**
- Tap Count: Shows number of registered taps
- Status: Displays current state (Ready/Tapping/Processing)
- Reset Taps button: Clear taps and start over

## API Endpoints

```
POST /api/tap
```
Register a beat tap
- Returns: tap_count, can_calculate

```
GET /api/tap/status
```
Get current tapper status
- Returns: tap_count, detected_bpm, detected_phase, etc.

```
POST /api/tap/reset
```
Reset all taps and cancel transitions

## Configuration

### BeatTapper Parameters

```python
BeatTapper(
    max_taps=32,       # Maximum taps to store
    min_taps=3,        # Minimum taps for BPM calculation
    timeout=1.5        # Seconds after last tap before processing
)
```

### PhaseTransitioner Parameters

```python
PhaseTransitioner(
    transition_duration=4.0  # Duration of smooth transition in seconds
)
```

## Technical Details

### Phase Calculation Formula

```python
frequency = bpm / 60.0
current_phase = (2 * π * frequency * time_since_music_start) % (2π)
phase_offset = -current_phase  # To align beat at phase = 0
```

### Easing Function

Ease-in-out cubic for smooth transitions:
```python
if progress < 0.5:
    eased = 4 * progress³
else:
    eased = 1 - pow(-2 * progress + 2, 3) / 2
```

### Outlier Filtering

Taps with intervals more than 1.5 standard deviations from the mean are filtered out to improve accuracy.

## Benefits

1. **User Control**: Manual override of automatic beat detection
2. **Real-time Adjustment**: Synchronize during playback
3. **Smooth Transitions**: Avoids sudden phase jumps
4. **Robust Detection**: Outlier filtering for accurate BPM
5. **Modular Design**: Easy to maintain and extend

## Future Enhancements

Possible improvements:
- Visual feedback (beat indicator animation)
- Adjustable transition duration
- Metronome output during tapping
- Save learned phase offsets per song
- Multiple phase offset profiles
