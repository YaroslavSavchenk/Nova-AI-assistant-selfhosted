"""Research package — news, Wikipedia, and URL summarization tools."""

from modules.research.news import NewsModule
from modules.research.wikipedia import WikipediaModule
from modules.research.summarize import SummarizeUrlModule

__all__ = ["NewsModule", "WikipediaModule", "SummarizeUrlModule"]
