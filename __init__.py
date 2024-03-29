from ovos_workshop.skills import OVOSSkill
from ovos_workshop.decorators import intent_handler
import time
from ovos_utils.log import LOG
from ovos_bus_client.message import Message
from ovos_workshop.decorators import killable_intent, killable_event
from .quiz_data import rounds_data
import random
import evdev
import selectors

class RonjaSkill(OVOSSkill):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    def initialize(self):
        self.current_round = 0
        self.stop_called = False
        self.skip_intro = False  # Initialize the variable
        self.keyboard_device = evdev.InputDevice("/dev/input/event7")
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.keyboard_device, selectors.EVENT_READ)


    def check_hardware_buttons(self):
        for key, events in self.selector.select(timeout=0.1):
            if events & selectors.EVENT_READ:
                for event in self.keyboard_device.read():
                    if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                        if event.code == evdev.ecodes.KEY_KPMINUS:  # NumMinus
                            self.skip_intro_intent()
                            #return 'stop'
                        elif event.code == evdev.ecodes.KEY_KPPLUS:  # NumPlus
                            return 'ja'
                        elif event.code == evdev.ecodes.KEY_KPENTER:  # NumEnter
                            return 'nee'
                        elif event.code == evdev.ecodes.KEY_KPSLASH:  # NumSlash
                            #return 'stop'
                            LOG.info(f"Slash pressed")                               
                            self.bus.emit(Message("mycroft.audio.speech.stop"))
                            self.stop()
        return None




    def generate_round_data(self, round_num):
        round_data = rounds_data.get(round_num)
        if round_data:
            questions = round_data['questions']
            correct_answers = round_data['correct_answers']
            question_audio_files = round_data['audio_files']['question_audio_files']

            # Convert relative paths to absolute paths
            question_audio_files = [self.root_dir + file_path for file_path in question_audio_files]
            for file_path in question_audio_files:
                LOG.info(f"Chosen audio file: {file_path}")

            combined = list(zip(questions, correct_answers, question_audio_files))
            random.shuffle(combined)
            questions, correct_answers, question_audio_files = zip(*combined)

            audio_files = round_data['audio_files']
            return (
                questions,
                correct_answers,
                question_audio_files,
                self.root_dir + audio_files['correct_answer_audio'],
                self.root_dir + audio_files['false_answer_audio'],
                self.root_dir + audio_files['intro'],
                self.root_dir + audio_files['outro'],
                self.root_dir + audio_files['main_question'],
                audio_files['duration_intro'],
                audio_files['duration_outro'],
                audio_files['duration_main'],
                audio_files['duration_correct'],
                audio_files['duration_false'],
                audio_files['duration_answers']
            )
        else:
            LOG.error(f"No data found for round {round_num}")
            return None

    @intent_handler("SkipIntro.intent")
    def skip_intro_intent(self):
        self.set_skip_intro(True)
        self.bus.emit(Message("mycroft.audio.speech.stop"))

    @intent_handler("StartQuiz.intent")
    @killable_intent(msg='recognizer_loop:wakeword')
    def start_quiz(self):
        self.play_game()

    def set_skip_intro(self, value):
        self.skip_intro = value

    def play_intro(self, intro, duration_intro):
        if not self.skip_intro:
            self.play_audio(intro)
            time_end = time.time() + duration_intro
            while time.time() < time_end and not self.skip_intro:
                response = self.check_hardware_buttons()
                if response == 'stop':
                    break
                time.sleep(0.1)

    def play_main_question(self, main_question, duration_main):
        self.play_audio(main_question)
        time.sleep(duration_main)

    def play_question_answer(self, question, question_audio_file, duration_answers):
        self.gui.show_text(question, override_idle=True)
        self.play_audio(question_audio_file)
        time.sleep(duration_answers)

    def play_correct_answer(self, correct_answer_audio, duration_correct):
        self.play_audio(correct_answer_audio)
        time.sleep(duration_correct)
        self.gui.show_text('Goed!', override_idle=True)

    def play_false_answer(self, false_answer_audio, duration_false):
        self.play_audio(false_answer_audio)
        self.gui.show_text('Ronja', override_idle=True)
        time.sleep(duration_false)

    def play_outro(self, outro, duration_outro):
        if outro:
            self.play_audio(outro)
            time_end = time.time() + duration_outro
            while time.time() < time_end and not self.skip_intro:
                response = self.check_hardware_buttons()
                if response == 'stop':
                    break
                time.sleep(0.1)

    def play_game(self):
        total_rounds = 12

        for round_num in range(0, total_rounds + 1):
            self.current_round = round_num

            self.gui.show_text(f"Round {round_num}:")
            self.gui.show_text("Ronja en de piraten", override_idle=True)

            questions, correct_answers, question_audio_files, correct_answer_audio, false_answer_audio, intro, outro, main_question, duration_intro, duration_outro, duration_main, duration_correct, duration_false, duration_answers = self.generate_round_data(round_num)

            intro_played = False

            for question, correct_answer, question_audio_file in zip(questions, correct_answers, question_audio_files):
                if not intro_played and not self.skip_intro:
                    self.play_intro(intro, duration_intro)
                    intro_played = True

                if intro_played:
                    self.play_main_question(main_question, duration_main)

                self.play_question_answer(question, question_audio_file, duration_answers)

                reply = None
                while reply not in ['ja', 'nee', 'stop']:
                    response = self.check_hardware_buttons()

                    if response:
                        reply = response.lower()
                    else:
                        # No need to prompt, just wait for hardware button response
                        time.sleep(0.1)


                if reply == 'ja' and correct_answer:
                    self.play_correct_answer(correct_answer_audio, duration_correct)
                    self.play_outro(outro, duration_outro)
                    break
                elif (reply == 'ja' and not correct_answer) or (reply == 'nee' and correct_answer):
                    self.play_false_answer(false_answer_audio, duration_false)
                    self.play_outro(outro, duration_outro)
                    break
                elif reply == 'stop':
                    return
                elif round_num == total_rounds:
                    self.gui.show_text('Einde', override_idle=True)
                    return

            self.set_skip_intro(False)

    def stop(self):
        time.sleep(2)
        self.gui.show_text('', override_idle=3)
        return
