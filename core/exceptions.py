class IBKRAPIError(Exception):
    def __init__(self, message="An error occurred in the Tickle API"):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return self.message
