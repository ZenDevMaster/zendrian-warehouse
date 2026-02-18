/**
 * Web Audio API Sound Playback
 *
 * Pre-loads sound files and plays them on demand.
 * Triggered by X-Play-Sound response header from HTMX requests.
 */

const SOUND_FILES = {
    bleep: '/static/sounds/bleep.mp3',
    error: '/static/sounds/error.mp3',
    success: '/static/sounds/success.mp3',
    newlocation: '/static/sounds/newlocation.mp3',
    deleted: '/static/sounds/deleted.mp3'
};

// Cache for loaded audio elements
const audioCache = {};

// Pre-load all sounds
document.addEventListener('DOMContentLoaded', function () {
    for (const [name, path] of Object.entries(SOUND_FILES)) {
        const audio = new Audio(path);
        audio.preload = 'auto';
        audio.load();
        audioCache[name] = audio;
    }
});

/**
 * Play a named sound effect.
 * @param {string} name - Sound name (bleep, error, success, newlocation, deleted)
 */
function playSound(name) {
    const audio = audioCache[name];
    if (!audio) {
        console.warn('Unknown sound:', name);
        return;
    }

    // Clone the audio node so overlapping plays work
    const clone = audio.cloneNode();
    clone.volume = 1.0;
    clone.play().catch(function (err) {
        // Browser may block autoplay until user interaction
        console.warn('Audio play blocked:', err.message);
    });
}
