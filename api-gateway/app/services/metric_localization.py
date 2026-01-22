"""
Localized display strings for metrics.

Provides a centralized mapping between internal metric codes and
their human-friendly Russian names for UI rendering and data seeding.
"""

from __future__ import annotations

from typing import Final

# Mapping MetricDef.code -> Russian display name used in UI
# Names use Title Case (first letter uppercase) for better readability
METRIC_DISPLAY_NAMES_RU: Final[dict[str, str]] = {
    # Общие
    "management_potential": "Потенциал к руководству",
    "management_motivation": "Мотивация к руководству",
    "general_intelligence": "Общий балл интеллекта",
    "conflict_prone": "Конфликтность",

    # Управленческие компетенции
    "management_decision_making": "Принятие управленческих решений",
    "systems_thinking": "Системное мышление",
    "influence": "Влияние",
    "delegation": "Делегирование",
    "control": "Контроль",
    "work_organization": "Организация работы",
    "leadership": "Лидерство",
    "business_communication": "Деловая коммуникация",

    # Роли по Адизесу
    "producer": "Производитель",
    "administrator": "Администратор",
    "entrepreneur": "Предприниматель",
    "integrator": "Интегратор",

    # Командные роли
    "idea_generator": "Генератор идей",
    "resource_investigator": "Исследователь ресурсов",
    "specialist": "Специалист",
    "analyst": "Аналитик",
    "coordinator": "Координатор",
    "motivator": "Мотиватор",
    "team_soul": "Душа команды",
    "implementer": "Реализатор",
    "controller": "Контролер",

    # Функциональные области
    "document_work": "Работа с документами",
    "promotion": "Продвижение",
    "analysis_planning": "Анализ и планирование",
    "decision_making": "Принятие решений",
    "development": "Разработка",
    "process_support": "Обеспечение процесса",
    "support": "Поддержка",
    "control_audit": "Контроль, аудит",
    "production_technology": "Производство и технологии",

    # Эмоциональные компетенции
    "achievement_motivation": "Мотивация достижений",
    "stress_resistance": "Стрессоустойчивость",

    # Социальные компетенции
    "client_orientation": "Ориентация на клиента",
    "communication_skills": "Коммуникабельность",
    "teamwork": "Командность",

    # Волевые компетенции
    "organization": "Организованность",
    "normativeness": "Нормативность",
    "responsibility": "Ответственность",

    # Когнитивные компетенции
    "innovativeness": "Инновационность",
    "complex_problem_solving": "Комплексное решение проблем",
    "self_development_motivation": "Стремление к саморазвитию",

    # Мотивация
    "external_motivation": "Внешняя мотивация",
    "internal_motivation": "Внутренняя мотивация",
    "interest_motivation": "Интерес",
    "creativity": "Творчество",
    "helping_people_motivation": "Помощь людям",
    "public_service_motivation": "Служение обществу",
    "communication": "Общение",
    "team_engagement": "Включенность в команду",
    "recognition_motivation": "Признание",
    "management": "Руководство",
    "money_motivation": "Деньги",
    "connections_motivation": "Связи",
    "health_motivation": "Здоровье",
    "traditions_motivation": "Традиции",

    # Структура интеллекта
    "calculations": "Вычисления",
    "vocabulary": "Лексика",
    "erudition": "Эрудиция",
    "spatial_thinking": "Пространственное мышление",
    "nonverbal_logic": "Невербальная логика",
    "verbal_logic": "Вербальная логика",
    "information_processing": "Обработка информации",

    # ПАРНЫЕ МЕТРИКИ (дефисный формат с en-dash)
    # Одиночные полюса удалены - используем только парные метрики
    # Блок ЛИЧНОСТЬ (11 пар)
    "introversion_sociability": "Замкнутость–Общительность",
    "passivity_activity": "Пассивность–Активность",
    "distrust_friendliness": "Недоверчивость–Дружелюбие",
    "independence_conformism": "Независимость–Конформизм",
    "moral_flexibility_morality": "Моральная гибкость–Моральность",
    "impulsiveness_organization": "Импульсивность–Организованность",
    "anxiety_stability": "Тревожность–Уравновешенность",
    "sensitivity_insensitivity": "Сензитивность–Нечувствительность",
    "intellectual_restraint_curiosity": "Интеллектуальная сдержанность–Любознательность",
    "traditionality_originality": "Традиционность–Оригинальность",
    "concreteness_abstractness": "Конкретность–Абстрактность",

    # Блок МОТИВАЦИЯ (1 пара)
    "external_internal_motivation": "Внешняя мотивация–Внутренняя мотивация",
}

# Mapping paired metric labels (left, right) -> metric code
# Used for normalizing paired metrics from various formats
# Keys are UPPERCASE for case-insensitive matching
PAIRED_METRICS: Final[dict[tuple[str, str], str]] = {
    # Блок ЛИЧНОСТЬ
    ("ЗАМКНУТОСТЬ", "ОБЩИТЕЛЬНОСТЬ"): "introversion_sociability",
    ("ПАССИВНОСТЬ", "АКТИВНОСТЬ"): "passivity_activity",
    ("НЕДОВЕРЧИВОСТЬ", "ДРУЖЕЛЮБИЕ"): "distrust_friendliness",
    ("НЕЗАВИСИМОСТЬ", "КОНФОРМИЗМ"): "independence_conformism",
    ("МОРАЛЬНАЯ ГИБКОСТЬ", "МОРАЛЬНОСТЬ"): "moral_flexibility_morality",
    ("ИМПУЛЬСИВНОСТЬ", "ОРГАНИЗОВАННОСТЬ"): "impulsiveness_organization",
    ("ТРЕВОЖНОСТЬ", "УРАВНОВЕШЕННОСТЬ"): "anxiety_stability",
    ("СЕНЗИТИВНОСТЬ", "НЕЧУВСТВИТЕЛЬНОСТЬ"): "sensitivity_insensitivity",
    ("ИНТЕЛЛЕКТУАЛЬНАЯ СДЕРЖАННОСТЬ", "ЛЮБОЗНАТЕЛЬНОСТЬ"): "intellectual_restraint_curiosity",
    ("ТРАДИЦИОННОСТЬ", "ОРИГИНАЛЬНОСТЬ"): "traditionality_originality",
    ("КОНКРЕТНОСТЬ", "АБСТРАКТНОСТЬ"): "concreteness_abstractness",

    # Блок МОТИВАЦИЯ
    ("ВНЕШНЯЯ МОТИВАЦИЯ", "ВНУТРЕННЯЯ МОТИВАЦИЯ"): "external_internal_motivation",
}


def normalize_paired_label(left: str, right: str) -> str | None:
    """
    Normalize paired metric labels to standard hyphenated format.

    Takes two parts of a paired metric (e.g., from "Замкнутость / Общительность")
    and returns the standardized display name with en-dash if it's a known pair.

    Args:
        left: Left part of the pair (e.g., "Замкнутость")
        right: Right part of the pair (e.g., "Общительность")

    Returns:
        Standard hyphenated display name (e.g., "Замкнутость–Общительность")
        or None if not a recognized pair
    """
    key = (left.upper().strip(), right.upper().strip())
    code = PAIRED_METRICS.get(key)
    if code:
        return METRIC_DISPLAY_NAMES_RU.get(code)
    return None


def get_metric_display_name_ru(code: str) -> str | None:
    """Return Russian display name for a metric code, if available."""
    return METRIC_DISPLAY_NAMES_RU.get(code)
