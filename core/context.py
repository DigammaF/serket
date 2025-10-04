
from __future__ import annotations

import logging
import json

from dataclasses import dataclass, field
from os import listdir
from pathlib import Path
from typing import Any, Callable
from re import compile, match
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from requests import Session, Response
from rich.console import Console, RenderableType
from rich.pretty import Pretty
from rich.panel import Panel
from rich.columns import Columns
from rich.progress import Progress

from .settings import CHUNK_SIZE
from .renderer import render
from .structure import DOWNLOADS, PROFILES, Profile, Tab

logger = logging.getLogger("serket.context")

HELP_COMMAND = compile(r"^help")
GET_COMMAND = compile(r"^get (?P<url>\S*)(?: as (?P<profile_name>\w*))?(?: to (?P<tab_name>\w*))?")
TABS_COMMAND = compile(r"^tabs")
TAB_COMMAND = compile(r"^tab (?P<selection>\S*)")
PROFILES_COMMAND = compile(r"^profiles")
PROFILE_COMMAND = compile(r"^profile (?P<name>\w*)")
SETTING_COMMAND = compile(r"^setting (?P<name>\S*) (?P<value>\S*)")
CLEAR_COOKIES_COMMAND = compile(r"^clear cookies")
FORK_PROFILE_COMMAND = compile(r"^fork profile (?P<name>\w*)")
DELETE_PROFILE_COMMAND = compile(r"^delete profile")

def decode_text(result: Response) -> str|None:
	encoding = result.encoding

	if encoding is None:
		encoding = result.apparent_encoding

	try:
		return str(result.content, encoding, errors="replace")

	except (LookupError, TypeError):
		return None

@dataclass
class Context:
	_profiles: dict[str, Profile] = field(init=False, default_factory=dict)
	_profile: Profile|None = field(default=None)
	_tab: Tab|None = field(default=None)
	_console: Console = field(default_factory=Console)
	_content_handlers: list[ContentHandler] = field(default_factory=list)

	class ContentHandler:
		def check(self, content_type: str) -> bool:
			result = self._check(content_type=content_type)
			logger.info(f"{self.__class__.__name__} checking '{content_type}': {result}")
			return result

		def _check(self, content_type: str) -> bool:
			...

		def run(self, profile: Profile, tab: Tab, result: Response, context: Context):
			logger.info(f"{self.__class__.__name__} running")
			self._run(profile=profile, tab=tab, result=result, context=context)

		def _run(self, profile: Profile, tab: Tab, result: Response, context: Context):
			...

	class HTMLHandler(ContentHandler):
		def _check(self, content_type: str) -> bool:
			return "text/html" in content_type
		
		def _run(self, profile: Profile, tab: Tab, result: Response, context: Context):
			text = decode_text(result)

			if text is None:
				context.error(f"could not decode content: encoding={result.encoding} apparent_encoding={result.apparent_encoding}")
				return

			document = BeautifulSoup(text, features="html.parser")
			tab.document = document
			profile.add_tab(tab)
			context._profile = profile
			context._tab = tab
			context.display_tab(tab)

	class JSONHandler(ContentHandler):
		def _check(self, content_type: str) -> bool:
			return "application/json" in content_type
		
		def run(self, profile: Profile, tab: Tab, result: Response, context: Context):
			text = decode_text(result)

			if text is None:
				context.error(f"could not decode content: encoding={result.encoding} apparent_encoding={result.apparent_encoding}")
				return

			context._console.print(text)

	class ImageHandler(ContentHandler):
		def _check(self, content_type: str) -> bool:
			return "image" in content_type
		
		def run(self, profile: Profile, tab: Tab, result: Response, context: Context):
			content_length = int(result.headers.get("content-length", 0))
			parsed_url = urlparse(result.url)
			path = Path(parsed_url.path)
			filename = path.stem + path.suffix

			if (user_filename := context._console.input(f"({filename}) overwrite filename: ")):
				filename = user_filename

			filepath = DOWNLOADS/filename

			try:
				with Progress() as progress:
					task = progress.add_task("Downloading", total=content_length)

					with open(filepath, "wb") as file:
						for chunk in result.iter_content(chunk_size=CHUNK_SIZE):
							file.write(chunk)
							progress.update(task, advance=len(chunk))

			except KeyboardInterrupt:
				context.error("Interrupted by user")
				return

			context.success(f"Downloaded to {filepath}")

	def __post_init__(self):
		self._content_handlers.extend((
			Context.HTMLHandler(), Context.JSONHandler(), Context.ImageHandler()
		))

	@property
	def prompt(self) -> str:
		profile = "no profile" if self._profile is None else f"[blue]{self._profile.name}[/blue]"
		tab = "no tab" if self._tab is None else f"[green]{self._tab.name} > {self._tab.title}[/green]"
		return f"({profile}|{tab}) "

	def info(self, text: str):
		logger.info(text)
		self._console.print(f"( ) {text}")

	def success(self, text: str):
		logger.info(f"success: {text}")
		self._console.print(f"[green](+)[/green] {text}")

	def error(self, text: str):
		logger.info(f"error: {text}")
		self._console.print(f"[red](!)[/red] {text}")

	def add_profile(self, profile: Profile):
		logger.info(f"adding profile '{profile.name}'")

		if profile.name in self._profiles:
			raise RuntimeError(f"'{profile.name}' already exists")
		
		self._profiles[profile.name] = profile

	def rem_profile(self, profile: Profile):
		logger.info(f"removing profile '{profile.name}'")
		del self._profiles[profile.name]

	def get_profile(self, profile_name: str) -> Profile:
		logger.info(f"getting profile '{profile_name}'")

		if profile_name in self._profiles:
			logger.info(f"found it in the loaded profiles")
			return self._profiles[profile_name]

		logger.info("creating an entry in the loaded profiles")
		profile = Profile(profile_name)
		profile.load_from_disk()
		self._profiles[profile_name] = profile
		return profile

	def display_tab(self, tab: Tab):
		logger.info(f"displaying tab '{tab.name}'")
		output = render(tab.document)
		self._console.print(output, markup=False)

	def get(self, url: str, profile_name: str|None, tab_name: str|None):
		logger.info(f"get {url=} {profile_name=} {tab_name=}")
		parsed_url = urlparse(url)
		logger.info(str(parsed_url))

		if parsed_url.scheme not in ("http", "https"):
			self.error(f"scheme '{parsed_url.scheme}' is not supported")
			return

		if not parsed_url.netloc:
			self.error(f"no netloc found in url")
			return
		
		if tab_name is None:
			tab_name = parsed_url.netloc
			logger.info(f"using auto tab name '{tab_name}'")

		profile: Profile

		if profile_name is None:
			if self._profile is None:
				self.error(f"no profile specified in command and no profile set as current")
				return

			logger.info(f"using current profile '{self._profile.name}'")
			profile = self._profile

		else:
			profile = self.get_profile(profile_name)

		profile.session.headers["User-Agent"] = profile.get_setting("user-agent")
		result = profile.session.get(url, stream=True)

		logger.info("request headers " + json.dumps(dict(profile.session.headers), indent=4))
		logger.info("response headers " + json.dumps(dict(result.headers), indent=4))
		
		content_type = result.headers.get("content-type", "no content type sent")
		content_length = int(result.headers.get("content-length", 0))
		self.info(f"status: {result.status_code} | type: {content_type} | size: {content_length}")

		if result.status_code == 200:
			tab = Tab(tab_name)

			for handler in self._content_handlers:
				if handler.check(content_type):
					handler.run(profile, tab, result, self)
					break

	def print_tabs(self):
		for profile_name, profile in self._profiles.items():
			if profile.tabs:
				panels = tuple(
					Panel.fit(
						tab.title,
						title=f"{key} / {tab.name}",
						style="yellow" if tab is self._tab else ""
					)
					for key, tab in profile.tabs.items()
				)
				self._console.print(Panel.fit(
					Columns(panels),
					title=profile_name,
					style="red" if profile is self._profile else ""
				))

	def change_tab(self, selection: str):
		if self._profile is None:
			self.error(f"No profile currently loaded")
			return

		key: int

		try: key = int(selection)
		except ValueError: key = -1

		if key == -1:
			logger.info(f"selecting tab by name '{selection}'")
			tab = self._profile.select_tab(selection)

			if tab is None:
				self.error(f"no tab has a name or title starting like that: '{selection}'")
				return

		else:
			logger.info(f"selecting tab by key {key}")

			if key in self._profile.tabs:
				tab = self._profile.tabs[key]

			else:
				self.error(f"no tab has this key: {key}")
				return

		self._tab = tab
		self.display_tab(tab)

	def print_profiles(self):
		logger.info("detecting profiles on disk")

		for filename in listdir(PROFILES):
			filepath = PROFILES/filename

			if filepath.suffix == ".profile":
				logger.info(f"found {filename} ({filepath.stem})")
				self.get_profile(filepath.stem)

			else:
				logger.info(f"ignoring {filename}")

		profile_renderables: list[RenderableType] = [ ]

		for profile_name, profile in self._profiles.items():
			settings = "\n".join(f"{name}: {value}" for name, value in profile.iter_settings())
			cookies = f"{len(profile.cookies)} cookies"
			profile_renderables.append(Panel.fit(
				f"{cookies}\n - settings - \n{settings}",
				title=profile_name,
				style="red" if profile is self._profile else ""
			))

		self._console.print(Columns(profile_renderables))

	def change_profile(self, name: str):
		if self._profile is not None: self._profile.save_to_disk()
		self._profile = self.get_profile(name)

	def set_setting(self, name: str, value: str):
		if self._profile is None:
			self.error(f"No profile currently loaded")
			return
		
		self._profile.set_setting(name, value)
		self.success("done")

	def clear_cookies(self):
		if self._profile is None:
			self.error(f"No profile currently loaded")
			return
		
		self._profile.clear_cookies()
		self.success("done")

	def fork_profile(self, name: str):
		self.error("not implemented")

	def delete_profile(self):
		if self._profile is None:
			self.error(f"No profile currently loaded")
			return
		
		self._profile.delete_from_disk()
		del self._profiles[self._profile.name]
		self._profile = None

	def print_help(self):
		self._console.print("[blue]help[/blue]: prints this help")
		self._console.print("[blue]get <url> (as <profile>)? (to <tab>)?[/blue]: visit <url>, using <profile> or the current one, sending the result to a new tab named <tab> or a new tab with an automatically picked name")
		self._console.print("[blue]tabs[/blue]: displays a list of active tabs and the profile used to open each one")
		self._console.print("[blue]tab <selection>[/blue]: switch to a tab by numerical key or by looking for a tab with a name or title starting with <selection>. Please note that you can only switch to tabs owned by your current profile")
		self._console.print("[blue]profiles[/blue]: prints a list of existing profiles")
		self._console.print("[blue]profile <name>[/blue]: switch to a profile, or create a new profile with that name if it doesn't exist")
		self._console.print("[blue]setting <name> <value>[/blue]: change a setting for the current profile")
		self._console.print("[blue]clear cookies[/blue]: clear all cookies from the current profile")
		self._console.print("[blue]fork profile <name>[/blue]: create a new profile named <name> by copying the settings and cookies of the current profile")
		self._console.print("[blue]delete profile[/blue]: delete the current profile from disk and memory")

	def process_command(self, command: str):
		logger.info(f"processing command '{command}'")

		if match(HELP_COMMAND, command) is not None:
			self.print_help()
			return

		if (hit := match(GET_COMMAND, command)) is not None:
			args = hit.groupdict()
			logger.info(f"GET: {dict(args)}")
			self.get(
				url=args["url"],
				profile_name=args.get("profile_name"),
				tab_name=args.get("tab_name")
			)
			return

		if match(TABS_COMMAND, command) is not None:
			self.print_tabs()
			return
		
		if (hit := match(TAB_COMMAND, command)) is not None:
			args = hit.groupdict()
			logger.info(f"TAB: {dict(args)}")
			self.change_tab(selection=args["selection"])
			return
		
		if match(PROFILES_COMMAND, command) is not None:
			self.print_profiles()
			return
		
		if (hit := match(PROFILE_COMMAND, command)) is not None:
			args = hit.groupdict()
			logger.info(f"PROFILE: {dict(args)}")
			self.change_profile(name=args["name"])
			return
		
		if (hit := match(SETTING_COMMAND, command)) is not None:
			args = hit.groupdict()
			logger.info(f"SETTING: {dict(args)}")
			self.set_setting(name=args["name"], value=args["value"])
			return
		
		if match(CLEAR_COOKIES_COMMAND, command) is not None:
			self.clear_cookies()
			return

		if (hit := match(FORK_PROFILE_COMMAND, command)) is not None:
			args = hit.groupdict()
			logger.info(f"FORK PROFILE: {dict(args)}")
			self.fork_profile(name=args["name"])
			return

		if match(DELETE_PROFILE_COMMAND, command) is not None:
			self.delete_profile()
			return

		self.error(f"not a known command")

	def mainloop(self):
		try:
			self._profile = self.get_profile("default")
			self._console.print(f"Welcome to [red]Serket[/red]! Use [red]help[/red] if needed.")

			while True:
				command = self._console.input(self.prompt)
				if not command: continue
				self.process_command(command)

		except KeyboardInterrupt:
			if self._profile is not None:
				self._profile.save_to_disk()

			self._console.print("\nBye bye! ^-^")
