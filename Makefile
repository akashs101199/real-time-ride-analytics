# Makefile for real-time-pipeline

SHELL := /bin/bash
COMPOSE := docker compose
PROJECT := real-time-pipeline

.PHONY: up down restart logs ps build clean stop pull

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down -v

restart: down up

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

build:
	$(COMPOSE) build --no-cache

pull:
	$(COMPOSE) pull

stop:
	$(COMPOSE) stop

clean: down
	docker builder prune -f
	docker system prune -f
