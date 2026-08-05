"""
Message Templates System
Supports dynamic message templates with variable substitution for Facebook posting
"""

import random
import re
import logging
from typing import List, Dict, Optional, Tuple
import json
import os

logger = logging.getLogger(__name__)

class MessageTemplateManager:
    """Manages message templates with variable substitution"""
    
    def __init__(self, templates_file='message_templates.json'):
        # Normalize to project-level templates_data/message_templates.json
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        default_path = os.path.join(base_dir, 'templates_data', 'message_templates.json')
        self.templates_file = templates_file
        if not os.path.isabs(self.templates_file):
            # If passed a relative path or default, point to shared templates_data
            self.templates_file = default_path
        self.default_variables = {
            "city": ["Цюрих", "Берн", "Люцерн", "Женева", "Базель", "Лозанна", "Винтертур"],
            "day": ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"],
            "time": ["утром", "днем", "вечером", "после обеда", "до обеда"],
            "mood": ["отличное", "прекрасное", "замечательное", "великолепное", "потрясающее"],
            "action": ["заходи", "присоединяйся", "не пропусти", "участвуй", "подключайся"],
            "company": ["наша команда", "мы", "наша организация", "наш коллектив"],
            "benefit": ["скидки", "бонусы", "подарки", "акции", "специальные предложения"],
            "emotion": ["🔥", "💡", "✨", "🎉", "💪", "🚀", "⭐"],
            "call_to_action": ["Звони сейчас!", "Пиши в личку!", "Оставляй заявку!", "Переходи по ссылке!"],
            "urgency": ["только сегодня", "ограниченное время", "до конца недели", "пока есть места"]
        }
        self.templates = []
        self.current_template_index = None
        self.current_variables = {}
        
        # Load templates from file if exists
        self.load_templates()
    
    def load_templates(self):
        """Load templates from JSON file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.templates_file), exist_ok=True)
            if os.path.exists(self.templates_file):
                with open(self.templates_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.templates = data.get('templates', [])
                    # Merge saved variables with defaults
                    saved_variables = data.get('variables', {})
                    for key, values in saved_variables.items():
                        if key in self.default_variables:
                            # Merge unique values
                            merged = list(set(self.default_variables[key] + values))
                            self.default_variables[key] = merged
                        else:
                            self.default_variables[key] = values
                logger.info(f"Loaded {len(self.templates)} templates from {self.templates_file}")
            else:
                # Create default templates
                self.create_default_templates()
                self.save_templates()
        except Exception as e:
            logger.error(f"Error loading templates: {e}")
            self.create_default_templates()
    
    def save_templates(self):
        """Save templates to JSON file"""
        try:
            data = {
                'templates': self.templates,
                'variables': self.default_variables
            }
            with open(self.templates_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved {len(self.templates)} templates to {self.templates_file}")
        except Exception as e:
            logger.error(f"Error saving templates: {e}")
    
    def create_default_templates(self):
        """Create default message templates"""
        self.templates = [
            "Привет! Мы работаем в {{city}} каждый {{day}} — {{action}}! {{emotion}}",
            "{{emotion}} Акция в {{city}}! Только {{urgency}} — не пропусти!",
            "💡 В {{city}} начинается новая неделя с {{benefit}}. Ждём в {{day}}!",
            "🚀 {{company}} предлагает {{benefit}} для жителей {{city}}. {{call_to_action}}",
            "{{emotion}} Настроение {{mood}}? Тогда {{action}} к нам в {{city}} в {{day}}!",
            "🎯 Специальное предложение в {{city}}! {{urgency}} — {{call_to_action}}",
            "✨ {{time}} в {{day}} у нас в {{city}} будет особенно интересно! {{action}}",
            "💪 {{company}} в {{city}} готова предложить вам {{benefit}}. {{urgency}}!",
            "🔥 Горячие {{benefit}} в {{city}}! Только для активных людей в {{day}}!",
            "⭐ Лучшие условия в {{city}} ждут вас {{time}} в {{day}}. {{call_to_action}}"
        ]
        logger.info("Created default message templates")
    
    def add_template(self, template: str) -> bool:
        """Add a new template"""
        try:
            if template and template.strip():
                self.templates.append(template.strip())
                self.save_templates()
                logger.info(f"Added new template: {template[:50]}...")
                return True
        except Exception as e:
            logger.error(f"Error adding template: {e}")
        return False
    
    def remove_template(self, index: int) -> bool:
        """Remove a template by index"""
        try:
            if 0 <= index < len(self.templates):
                removed = self.templates.pop(index)
                self.save_templates()
                logger.info(f"Removed template: {removed[:50]}...")
                return True
        except Exception as e:
            logger.error(f"Error removing template: {e}")
        return False
    
    def delete_template(self, index: int) -> str:
        """Delete a template by index and return the deleted template"""
        if 0 <= index < len(self.templates):
            deleted = self.templates.pop(index)
            self.save_templates()
            logger.info(f"Deleted template #{index}: {deleted[:50]}...")
            return deleted
        else:
            raise IndexError(f"Template index {index} out of range")
    
    def delete_multiple_templates(self, indices: List[int]) -> List[str]:
        """Delete multiple templates by indices"""
        # Sort indices in descending order to avoid index shifting
        sorted_indices = sorted(set(indices), reverse=True)
        deleted_templates = []
        
        for index in sorted_indices:
            if 0 <= index < len(self.templates):
                deleted = self.templates.pop(index)
                deleted_templates.append(deleted)
        
        if deleted_templates:
            self.save_templates()
            logger.info(f"Deleted {len(deleted_templates)} templates")
        
        return deleted_templates
    
    def get_template_list(self) -> List[Dict]:
        """Get list of all templates with their indices"""
        return [{'index': i, 'template': template} for i, template in enumerate(self.templates)]
    
    def has_templates(self) -> bool:
        """Check if there are any templates available"""
        return len(self.templates) > 0
    
    def update_variables(self, variables: Dict[str, List[str]]):
        """Update variables dictionary"""
        try:
            self.default_variables.update(variables)
            self.save_templates()
            logger.info("Variables updated successfully")
        except Exception as e:
            logger.error(f"Error updating variables: {e}")
    
    def add_variable_option(self, variable_name: str, option: str) -> bool:
        """Add a new option to a variable"""
        try:
            if variable_name not in self.default_variables:
                self.default_variables[variable_name] = []
            
            if option not in self.default_variables[variable_name]:
                self.default_variables[variable_name].append(option)
                self.save_templates()
                logger.info(f"Added option '{option}' to variable '{variable_name}'")
                return True
        except Exception as e:
            logger.error(f"Error adding variable option: {e}")
        return False
    
    def get_template_variables(self, template: str) -> List[str]:
        """Extract variables from a template, supporting both {city} and {{city}}."""
        matches = re.findall(r'\{\{([^}]+)\}\}|\{([^{}]+)\}', template)
        variables = []
        for double_brace_var, single_brace_var in matches:
            variable = (double_brace_var or single_brace_var or '').strip()
            if variable and '|' not in variable and variable not in variables:
                variables.append(variable)
        return variables

    def expand_spintax(self, template: str) -> str:
        """Expand simple spintax patterns like {hello|hi|hey} before variable substitution."""
        message = template
        spin_pattern = re.compile(r'\{([^{}|]+\|[^{}]+)\}')
        guard = 0
        while guard < 50 and spin_pattern.search(message):
            guard += 1

            def _replace(match):
                options = [part.strip() for part in match.group(1).split('|') if part.strip()]
                return random.choice(options) if options else match.group(0)

            message = spin_pattern.sub(_replace, message)
        return message

    def anti_duplicate_score(self, message: str) -> float:
        """Return a rough uniqueness score against saved templates."""
        target_words = set(re.findall(r'\w+', (message or '').lower()))
        if not target_words:
            return 1.0
        max_similarity = 0.0
        for template in self.templates:
            words = set(re.findall(r'\w+', template.lower()))
            if not words:
                continue
            similarity = len(target_words & words) / max(1, len(target_words | words))
            max_similarity = max(max_similarity, similarity)
        return round(1.0 - max_similarity, 4)
    
    def substitute_variables(self, template: str, custom_variables: Optional[Dict[str, str]] = None) -> Tuple[str, Dict[str, str]]:
        """
        Substitute variables in template with random values
        
        Args:
            template: Template string with {{variable}} placeholders
            custom_variables: Optional custom variable values to use
            
        Returns:
            Tuple of (substituted_message, used_variables)
        """
        used_variables = {}
        message = self.expand_spintax(template)
        
        # Find all variables in template
        variables = self.get_template_variables(template)
        
        for var in variables:
            if custom_variables and var in custom_variables:
                # Use custom value
                value = custom_variables[var]
            elif var in self.default_variables:
                # Use random value from defaults
                value = random.choice(self.default_variables[var])
            else:
                # Unknown variable, leave placeholder
                logger.warning(f"Unknown variable: {var}")
                value = f"{{{{var}}}}"
            
            used_variables[var] = value
            message = message.replace(f"{{{{{var}}}}}", value)
            message = message.replace(f"{{{var}}}", value)
        
        return message, used_variables
    
    def generate_message(self, template_index: Optional[int] = None, custom_variables: Optional[Dict[str, str]] = None) -> Tuple[str, int, Dict[str, str]]:
        """
        Generate a message from templates
        
        Args:
            template_index: Specific template to use (None for random)
            custom_variables: Custom variable values
            
        Returns:
            Tuple of (final_message, template_index_used, variables_used)
        """
        if not self.templates:
            raise ValueError("No templates available")
        
        # Select template
        if template_index is not None and 0 <= template_index < len(self.templates):
            selected_index = template_index
        else:
            selected_index = random.randint(0, len(self.templates) - 1)
        
        template = self.templates[selected_index]
        
        # Substitute variables
        final_message, used_variables = self.substitute_variables(template, custom_variables)
        
        # Store current state for logging
        self.current_template_index = selected_index
        self.current_variables = used_variables
        
        used_variables['anti_duplicate_score'] = self.anti_duplicate_score(final_message)
        return final_message, selected_index, used_variables
    
    def validate_template(self, template: str) -> Tuple[bool, List[str]]:
        """
        Validate a template string
        
        Returns:
            Tuple of (is_valid, list_of_warnings)
        """
        warnings = []
        
        if not template.strip():
            return False, ["Template cannot be empty"]
        
        # Check for malformed variables
        if template.count('{{') != template.count('}}'):
            warnings.append("Mismatched variable brackets {{ }}")
        
        # Check for unknown variables
        variables = self.get_template_variables(template)
        unknown_vars = [var for var in variables if var not in self.default_variables]
        if unknown_vars:
            warnings.append(f"Unknown variables: {', '.join(unknown_vars)}")
        
        # Check template length
        if len(template) > 1000:
            warnings.append("Template is very long (>1000 chars)")
        
        # Check for nested variables
        if '{{' in template.replace('{{', '').replace('}}', ''):
            warnings.append("Possible nested variables detected")
        
        return len(warnings) == 0 or all('Unknown variables' not in w for w in warnings), warnings
    
    def get_stats(self) -> Dict:
        """Get template system statistics"""
        total_combinations = 1
        for var_list in self.default_variables.values():
            total_combinations *= len(var_list)
        
        return {
            'total_templates': len(self.templates),
            'total_variables': len(self.default_variables),
            'total_variable_options': sum(len(options) for options in self.default_variables.values()),
            'possible_combinations': total_combinations,
            'current_template_index': self.current_template_index,
            'last_used_variables': self.current_variables
        }
    
    def preview_templates(self, count: int = 3) -> List[Dict]:
        """Generate preview of random template variations"""
        previews = []
        
        for i in range(min(count, len(self.templates))):
            try:
                message, template_idx, variables = self.generate_message()
                previews.append({
                    'template_index': template_idx,
                    'original_template': self.templates[template_idx],
                    'generated_message': message,
                    'variables_used': variables
                })
            except Exception as e:
                logger.error(f"Error generating preview {i}: {e}")
        
        return previews

# Global instance
template_manager = MessageTemplateManager()

def get_template_manager() -> MessageTemplateManager:
    """Get the global template manager instance"""
    return template_manager 