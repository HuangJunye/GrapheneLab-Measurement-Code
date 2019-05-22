from .lock_in_amplifier import LockInAmplifier


class SR850(LockInAmplifier):

    def __init__(self, address):
        super().__init__(address)
        self.name = 'SR850'

