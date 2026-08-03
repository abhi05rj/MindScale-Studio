class ContentEngine:

    def __init__(self):
        self.name = "MindScale Content Engine"

    def generate_post(self, idea):

        post = {
            "title": idea["title"],
            "hook": idea["hook"],
            "script": f"Today we're exploring: {idea['title']}",
            "cta": "Follow for more mind-blowing content!",
            "visual_direction": idea["visual_direction"]
        }

        return post