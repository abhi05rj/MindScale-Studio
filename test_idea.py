from app.idea_engine.idea_generator import IdeaGenerator

idea_engine = IdeaGenerator()

idea = idea_engine.generate_idea()

print(idea)