import math
import wave
import winsound
from array import array
from pathlib import Path
from tempfile import TemporaryDirectory


NOTES = {"micro_start": (523, 392), "resume_focus": (392, 587),
         "long_start": (523, 440, 330), "long_end": (392, 494, 659),
         "complete": (392, 494, 659)}


NOTES.update(start=(349,494),short_start=(494,392),short_end=(392,523),manual_start=(440,349),
             manual_end=(349,440),rest_hint=(440,),auto_start=(392,523,587))


class Chimes:
    def __init__(self, directory):
        self.cache = TemporaryDirectory(prefix="audio-",dir=directory)

    def play(self, event, settings):
        if not settings.audio or not settings.volume or event not in NOTES:
            return
        path = Path(self.cache.name) / f"{event}-{settings.voice}-{settings.volume}.wav"
        if not path.exists():
            rate = 22050
            notes = NOTES[event]
            samples = array("h")
            decay, harmonic = {"纯音": (4, 0), "柔钟": (4, 0.16), "木琴": (8, 0.22)}[settings.voice]
            for i in range(round((0.6 + 0.17*(len(notes)-1)) * rate)):
                t = i/rate
                value = 0.
                for n, hz in enumerate(notes):
                    s = t - n*0.17
                    if 0 < s < 0.6:
                        env = min(1, s/.018, (.6-s)/.08) * math.exp(-decay*s)
                        phase = 2*math.pi*s*hz
                        value += env*(math.sin(phase)+harmonic*math.sin(2*phase))
                samples.append(round(value * 6200 * settings.volume / 100))
            with wave.open(str(path), "wb") as out:
                out.setparams((1,2,rate,0,"NONE","not compressed"))
                out.writeframes(samples.tobytes())
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)

    def close(self):
        winsound.PlaySound(None, 0)
        self.cache.cleanup()
