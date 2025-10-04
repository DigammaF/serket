
from __future__ import annotations

import pickle
import json
import logging

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from requests.sessions import RequestsCookieJar, Session
from bs4 import BeautifulSoup

from .result import Result, Ok, Error

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
PROXIES = require(BASE/"proxies")

logger.info(f"\n{BASE=}\n{COOKIES=}\n{DOWNLOADS=}\n{PROFILES=}\n{PROXIES=}")

DEFAULT_SETTINGS: dict[str, str] = {
	"user-agent": "Mozilla/5.0 (X11; Ubuntu; NoPointer) Gecko/20100101 Serket/0.1"
}

@dataclass
class Profile:
	_name: str
	_session: Session = field(default_factory=Session)
	_tabs: dict[int, Tab] = field(init=False, default_factory=dict)
	_settings: dict[str, str] = field(default_factory=dict)
	_proxies: dict[str, str] = field(default_factory=dict)

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
	
	@property
	def proxies_file(self) -> Path:
		return PROXIES/f"{self._name}.proxies"
	
	@property
	def is_stored_on_disk(self) -> bool:
		result = self.profile_file.exists()
		logger.info(f"checking if profile '{self._name}' exists by checking existence of {self.profile_file}: {result}")
		return result
	
	def get_setting(self, name: str) -> Result[str, str]:
		if name in self._settings: return Ok(self._settings[name])
		return Error(f"no such setting '{name}'")
	
	def set_setting(self, name: str, value: str) -> Result[str, str]:
		logger.info(f"profile '{self._name}': setting '{name}' set to '{value}'")
		if name in self._settings: message = f"changed '{name}' to '{value}'"
		else: message = f"created '{name}' with '{value}'"
		self._settings[name] = value
		return Ok(message)

	def iter_settings(self) -> Iterable[tuple[str, str]]:
		return iter(self._settings.items())
	
	def reset_setting(self, name: str) -> Result[str, str]:
		if name in DEFAULT_SETTINGS:
			self._settings[name] = DEFAULT_SETTINGS[name]
			return Ok(f"reset setting '{name}' to '{DEFAULT_SETTINGS[name]}'")
		
		return Error(f"no default available for '{name}'")

	def get_proxy(self, scheme: str) -> Result[str, str]:
		if scheme in self._proxies: return Ok(self._proxies[scheme])
		return Error(f"no proxy defined for '{scheme}'")
	
	def set_proxy(self, scheme: str, value: str) -> Result[str, str]:
		if scheme in self._proxies: message = f"set proxy for '{scheme}' to '{value}'"
		else: message = f"created proxy for '{scheme}' to '{value}'"
		self._proxies[scheme] = value
		return Ok(message)

	def iter_proxies(self) -> Iterable[tuple[str, str]]:
		return iter(self._proxies.items())
	
	def clear_proxy(self, scheme: str) -> Result[str, str]:
		if scheme in self._proxies:
			del self._proxies[scheme]
			return Ok(f"cleared '{scheme}'")
		
		return Ok(f"'{scheme}' did not exist anyway")

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

	def _load_proxies(self):
		logger.info(f"profile '{self._name}': loading proxies")
		logger.info(f"checking {self.proxies_file}")

		if self.proxies_file.exists():
			logger.info(f"file exists")

			with open(self.proxies_file, "r", encoding="utf-8") as file:
				loaded = json.load(file)
				logger.info(f"loading those proxies " + json.dumps(loaded, indent=4))
				self._proxies.update(loaded)
				return
			
		else:
			logger.info(f"file not found, not loading any proxy")
			return
		
	def _save_proxies(self):
		logger.info(f"profile '{self._name}': saving proxies to {self.proxies_file}")

		with open(self.proxies_file, "w", encoding="utf-8") as file:
			json.dump(self._proxies, file, indent=4)

	def load_from_disk(self):
		self._load_cookies()
		self._load_profile_settings()
		self._load_proxies()

	def save_to_disk(self):
		self._save_cookies()
		self._save_profile_settings()
		self._save_proxies()

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
