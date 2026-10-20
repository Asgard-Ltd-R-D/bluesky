""" HITL screen recorder.

    Records the operator's whole screen (desktop) to an MP4 file while a
    scenario runs, so the recording can later be aligned with the other
    HITL logs and with the EEG data.

    The recording itself is done by an external ffmpeg process (Windows
    'gdigrab' desktop capture), started and stopped from here - the sim
    loop never touches video frames, so recording does not slow it down.
    The ffmpeg binary comes from the 'imageio-ffmpeg' pip package
    (pip install imageio-ffmpeg); an ffmpeg on the PATH is used as a
    fallback.

    Next to the video, a SCREENRECLOG CSV is written, one row per
    simulation second: simulation time, the matching time into the video,
    and the wall-clock (unix) time. That is the bridge between the simt
    clock used by every other HITL logger and the video's own clock
    (they drift apart whenever the sim is paused or fast-forwarded).

    Load with:   PLUGINS LOAD HITL_SCREENREC   (or add 'hitl_screenrec'
                 to enabled_plugins in settings.cfg, same as the other
                 HITL loggers)
    Start with:  SCREENREC ON   (starts a fresh video + SCREENRECLOG;
                 put it in the scenario, after the reset, same as
                 FOVACLOG/OPCMDLOG/HITLCONFLOG/HEARTBEATLOG)
    Stop with:   SCREENREC OFF  (also stopped automatically on every sim
                 reset, i.e. when a scenario is (re)loaded, and at quit)

    Note: the sim process does the capturing, so this only works when
    the sim runs on the same machine as the operator's screen (the
    normal 'python BlueSky.py' setup).
"""
import atexit
import shutil
import subprocess
import time

import bluesky as bs
from bluesky import settings, stack
from bluesky.tools import datalog
from bluesky.core import Entity, timed_function

settings.set_variable_defaults(screenrec_fps=15)

screenrecheader = \
    '#######################################################\n' + \
    'SCREENRECLOG\n' + \
    'Simulation time vs. screen-recording time, one row per\n' + \
    'simulation second while SCREENREC is on.\n' + \
    '#######################################################\n\n' + \
    'Parameters [Units]:\n' + \
    'Simulation time [s], ' + \
    'Video time [s], ' + \
    'Wall-clock time [s since 1970-01-01 UTC]\n'

screenrec = None


def find_ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which('ffmpeg')


def init_plugin():
    global screenrec
    screenrec = HitlScreenrec()

    config = {
        'plugin_name':     'HITL_SCREENREC',
        'plugin_type':     'sim'
    }
    stackfunctions = {}
    return config, stackfunctions


class HitlScreenrec(Entity):
    def __init__(self):
        super().__init__()
        self.logger = datalog.crelog('SCREENRECLOG', None, screenrecheader)
        self.proc = None
        self.fname = None
        self.t0 = 0.0
        atexit.register(self.stop)

    @stack.command(name='SCREENREC')
    def screenrec(self, flag: 'onoff' = None):
        ''' SCREENREC ON/OFF: Record the screen to an MP4 file in the
            output folder, with a SCREENRECLOG CSV to align it to simt. '''
        if flag is None:
            if self.proc:
                return True, f'SCREENREC is ON, recording to {self.fname}'
            return True, 'SCREENREC is OFF'
        if not flag:
            self.stop()
            return True, 'SCREENREC stopped'
        return self.start()

    def start(self):
        # Always a fresh file, even if a recording was already running
        self.stop()
        ffmpeg = find_ffmpeg()
        if ffmpeg is None:
            return False, 'SCREENREC: ffmpeg not found - run ' + \
                          '"pip install imageio-ffmpeg" in the BlueSky venv'

        self.fname = datalog.makeLogfileName('SCREENREC').with_suffix('.mp4')
        self.fname.parent.mkdir(parents=True, exist_ok=True)
        ffmpeglog = open(self.fname.with_suffix('.ffmpeg.txt'), 'w')
        cmd = [ffmpeg, '-y', '-loglevel', 'warning',
               '-f', 'gdigrab', '-framerate', str(settings.screenrec_fps),
               '-draw_mouse', '1', '-i', 'desktop',
               '-c:v', 'libx264', '-preset', 'ultrafast',
               '-pix_fmt', 'yuv420p',
               # libx264 needs even frame dimensions
               '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',
               # Fragmented MP4: the file stays playable even if ffmpeg
               # is killed instead of stopped cleanly
               '-movflags', '+frag_keyframe+empty_moov',
               str(self.fname)]
        try:
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=ffmpeglog,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except OSError as e:
            ffmpeglog.close()
            self.proc = None
            return False, f'SCREENREC: could not start ffmpeg: {e}'
        ffmpeglog.close()
        self.t0 = time.time()

        self.logger.start()
        self.log_sync()
        return True, f'SCREENREC recording to {self.fname}'

    def stop(self):
        if self.proc is None:
            return
        proc, self.proc = self.proc, None
        try:
            # 'q' on stdin makes ffmpeg finish the file cleanly
            proc.stdin.write(b'q')
            proc.stdin.flush()
            proc.stdin.close()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        self.logger.reset()

    def log_sync(self):
        now = time.time()
        self.logger.log(now - self.t0, now)

    @timed_function(name='HITL_SCREENREC', dt=1.0)
    def update(self, dt):
        if self.proc is None:
            return
        if self.proc.poll() is not None:
            stack.stack(f'ECHO SCREENREC: ffmpeg stopped unexpectedly, '
                        f'see {self.fname.with_suffix(".ffmpeg.txt").name}')
            self.proc = None
            self.logger.reset()
            return
        self.log_sync()

    @timed_function(name='HITL_SCREENREC.reset', hook='reset')
    def reset(self):
        """ Stop any running recording on sim reset (scenario load), so
            every run gets its own video when the scenario turns
            SCREENREC on again. """
        self.stop()
