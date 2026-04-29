from enum import Enum


class EmailSendingStrategy(Enum):
    LOCAL = "local"
    MAILHOG = "mailhog"
    MAILTRAP = "mailtrap"
