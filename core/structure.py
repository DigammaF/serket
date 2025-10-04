
from __future__ import annotations

import pickle
import json
import logging

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from requests.sessions import RequestsCookieJar, Session
from bs4 import BeautifulSoup

logger = logging.getLogger("serket.structure")

BASE = Path(__file__).parent.resolve().parent

def require(folder: Path) -> Path:
	if not folder.exists():
		logger.info(f"creating {folder}")
		folder.mkdir()

	return folder

COOKIES = require(BASE/"cookies")
DOWNLOADS = require(BASE/"downloads")
PROFILES = require(BASE/"profiles")

logger.info(f"\n{BASE=}\n{COOKIES=}\n{DOWNLOADS=}\n{PROFILES=}")

DEFAULT_SETTINGS: dict[str, str] = {
	"user-agent": "Mozilla/5.0 (X11; Ubuntu; NoPointer) Gecko/20100101 Serket/0.1"
}

@dataclass
class Profile:
	_name: str
	_session: Session = field(default_factory=Session)
	_tabs: dict[int, Tab] = field(init=False, default_factory=dict)
	_settings: dict[str, str] = field(default_factory=dict)

	def __post_init__(self):
		if not self._name: raise RuntimeError(f"tried to create a profile with no name")
		
		for key, default in DEFAULT_SETTINGS.items():
			if key not in self._settings:
				self._settings[key] = default

	@property
	def name(self) -> str:
		return self._name

	@property
	def cookies_file(self) -> Path:
		return COOKIES/f"{self._name}.cookies"
	
	@property
	def session(self) -> Session:
		return self._session
	
	@property
	def cookies(self) -> RequestsCookieJar:
		return self._session.cookies

	@property
	def tabs(self) -> dict[int, Tab]:
		return self._tabs
	
	@property
	def profile_file(self) -> Path:
		return PROFILES/f"{self._name}.profile"
	
	def get_setting(self, name: str) -> str:
		return self._settings[name]
	
	def set_setting(self, name: str, value: str):
		logger.info(f"profile '{self._name}': setting '{name}' set to '{value}'")
		self._settings[name] = value

	def iter_settings(self) -> Iterable[tuple[str, str]]:
		return iter(self._settings.items())

	def clear_cookies(self):
		logger.info(f"profile '{self._name}': clearing cookies")
		self._session.cookies = RequestsCookieJar()

	def _load_cookies(self):
		logger.info(f"profile '{self._name}': loading cookies")
		logger.info(f"checking {self.cookies_file}")

		if self.cookies_file.exists():
			logger.info(f"file exists")

			with open(self.cookies_file, "rb") as file:
				cookies = pickle.load(file)
				logger.info(f"found an object of type {cookies.__class__.__name__}")
				assert isinstance(cookies, RequestsCookieJar)
				self._session.cookies = cookies
				return

		else:
			logger.info(f"using new cookies")
			self._session.cookies = RequestsCookieJar()
			return
		
	def _save_cookies(self):
		logger.info(f"profile '{self._name}': saving cookies to {self.cookies_file}")

		with open(self.cookies_file, "wb") as file:
			pickle.dump(self._session.cookies, file)

	def _load_profile_settings(self):
		logger.info(f"profile '{self._name}': loading profile settings")
		logger.info(f"checking {self.profile_file}")

		if self.profile_file.exists():
			logger.info(f"file exists")

			with open(self.profile_file, "r", encoding="utf-8") as file:
				loaded = json.load(file)
				logger.info(f"loading those settings " + json.dumps(loaded, indent=4))
				self._settings.update(loaded)
				return
			
		else:
			logger.info(f"using default settings")

			for key, default in DEFAULT_SETTINGS.items():
				if key not in self._settings:
					self._settings[key] = default

			return

	def _save_profile_settings(self):
		logger.info(f"profile '{self._name}': saving profile settings to {self.profile_file}")

		with open(self.profile_file, "w", encoding="utf-8") as file:
			json.dump(self._settings, file, indent=4)

	def load_from_disk(self):
		self._load_cookies()
		self._load_profile_settings()

	def save_to_disk(self):
		self._save_cookies()
		self._save_profile_settings()

	def delete_from_disk(self):
		logger.info(f"profile '{self._name}': deleting profile from disk")
		
		if self.cookies_file.exists():
			logger.info(f"deleting {self.cookies_file}")
			self.cookies_file.unlink()

		if self.profile_file.exists():
			logger.info(f"deleting {self.profile_file}")
			self.profile_file.unlink()

	def add_tab(self, tab: Tab):
		logger.info(f"profile '{self._name}': adding tab '{tab.name}'")
		n: int = 0
		while n in self._tabs: n += 1
		self._tabs[n] = tab

	def rem_tab(self, key: int):
		logger.info(f"profile '{self._name}': removing tab number {key}")
		tab = self._tabs[key]
		logger.info(f"turns out to be the tab '{tab.name}'")
		del self._tabs[key]

	def select_tab(self, selection: str) -> Tab|None:
		logger.info(f"profile '{self._name}': looking for tab '{selection}'")

		for tab in self._tabs.values():
			if tab.name.lower().startswith(selection.lower()) or tab.title.lower().startswith(selection.lower()):
				logger.info(f"found '{tab.name}'")
				return tab

@dataclass
class Tab:
	_name: str
	_document: BeautifulSoup = field(default_factory=BeautifulSoup)

	@property
	def name(self) -> str:
		return self._name

	@property
	def document(self) -> BeautifulSoup:
		return self._document
	
	@property
	def title(self) -> str:
		title = self._document.title
		if title is None: return ""
		else: return title.get_text()
	
	@document.setter
	def document(self, value: BeautifulSoup):
		logger.info(f"tab '{self.name}': setting document")
		self._document = value
