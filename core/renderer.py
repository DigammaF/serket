
from bs4 import BeautifulSoup
from rich.console import RenderableType, Group
from rich.panel import Panel
from rich.markdown import Markdown

def render(document: BeautifulSoup) -> RenderableType:
	renderables: list[RenderableType] = [ ]

	for paragraph in document.find_all("p"):
		text = paragraph.get_text()

		if len(text) > 50:
			renderables.append(Panel.fit(text))

	return Group(*renderables)

	#return document.get_text()
