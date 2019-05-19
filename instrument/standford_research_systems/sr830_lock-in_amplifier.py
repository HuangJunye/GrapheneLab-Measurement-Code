from . import lock-in_amplifier

class SR830(LockInAmplifier):

    # Print a description string
    def description(self):
        description_string = "SR830"
        for item in list(vars(self).items()):
            if item[0] == "tau" or item[0] == "excitation" or item[0] == "frequency" \
                    or item[0] == "harmonic" or item[0] == "address" or item[0] == "phase" \
                    or item[0] == "sensitivity" or item[0] == "internal_excitation":
                description_string = ", ".join((description_string, "%s = %.3f" % item))

        description_string = "".join((description_string, "\n"))
        return description_string