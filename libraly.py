#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Училищна библиотека - административна програма (само Python + tkinter)."""

import csv
import json
import logging
import os
import shutil
import sys
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "library_data.json")
LOG_FILE = os.path.join(BASE_DIR, "library.log")

LOAN_DAYS = 14                      # срок за връщане (дни)
DATE_FMT = "%Y-%m-%d %H:%M"
DAY_FMT = "%Y-%m-%d"


# ----------------------------------------------------------------------------
# Помощни функции
# ----------------------------------------------------------------------------

def normalize_grade(value):
    """Връща клас като низ '1'..'12' или None, ако е невалиден."""
    value = str(value).strip()
    if not value.isdigit():
        return None
    grade = int(value)
    if grade < 1 or grade > 12:
        return None
    return str(grade)


def default_graduation_year(grade, today=None):
    """Година на випуска според класа (учебната година започва през септември)."""
    today = today or datetime.now()
    start_year = today.year if today.month >= 9 else today.year - 1
    return start_year + 1 + (12 - int(grade))


def student_class(student):
    if not student:
        return "—"
    grade = str(student.get("grade", "")).strip()
    section = str(student.get("section", "")).strip().upper()
    return f"{grade}{section}" if grade else "—"


def loan_due(loan):
    due = loan.get("due_date")
    if due:
        return due
    try:
        start = datetime.strptime(loan.get("date", ""), DATE_FMT)
        return (start + timedelta(days=LOAN_DAYS)).strftime(DAY_FMT)
    except ValueError:
        return ""


def is_overdue(loan):
    if loan.get("returned"):
        return False
    due = loan_due(loan)
    return bool(due) and due < datetime.now().strftime(DAY_FMT)


def sort_tree(tree, col, reverse):
    """Сортиране на таблица при клик върху заглавие на колона."""
    rows = [(tree.set(k, col), k) for k in tree.get_children("")]

    def sort_key(item):
        value = item[0]
        try:
            return (0, float(value), "")
        except ValueError:
            return (1, 0.0, value.lower())

    rows.sort(key=sort_key, reverse=reverse)
    for index, (_, k) in enumerate(rows):
        tree.move(k, "", index)
    tree.heading(col, command=lambda: sort_tree(tree, col, not reverse))


# ----------------------------------------------------------------------------
# Данни
# ----------------------------------------------------------------------------

class Library:
    """Данни и бизнес логика (без графичен интерфейс)."""

    def __init__(self, path):
        self.path = path
        self.books = []
        self.students = []
        self.loans = []

    # ---------- зареждане / записване ----------

    def load(self):
        """Зарежда данните. Връща текст на грешка или None."""
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, "r", encoding="utf-8") as file:
                raw = json.load(file)
            if not isinstance(raw, dict):
                raise ValueError("Невалиден формат на данните.")
            self.books = self._dicts(raw.get("books"))
            self.students = self._dicts(raw.get("students"))
            self.loans = self._dicts(raw.get("loans"))
            self._normalize()
        except Exception as exc:  # noqa: BLE001
            logging.exception("Грешка при зареждане на данните.")
            # Запазваме повредения файл, за да не бъде презаписан и изгубен.
            try:
                shutil.copy2(self.path, self.path + ".broken")
            except OSError:
                pass
            self.books, self.students, self.loans = [], [], []
            return str(exc)
        return None

    def save(self):
        """Безопасен запис: временен файл + резервно копие."""
        tmp_path = self.path + ".tmp"
        payload = {
            "books": self.books,
            "students": self.students,
            "loans": self.loans,
        }
        with open(tmp_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=4)
        if os.path.exists(self.path):
            shutil.copy2(self.path, self.path + ".bak")
        os.replace(tmp_path, self.path)
        logging.info("Данните са записани.")

    @staticmethod
    def _dicts(value):
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _fix_ids(items):
        used = set()
        need_new = []
        for item in items:
            try:
                number = int(item.get("id"))
            except (TypeError, ValueError):
                number = None
            if number is None or number in used:
                need_new.append(item)
            else:
                item["id"] = number
                used.add(number)
        next_number = max(used, default=0) + 1
        for item in need_new:
            item["id"] = next_number
            next_number += 1

    def _normalize(self):
        self._fix_ids(self.books)
        self._fix_ids(self.students)
        self._fix_ids(self.loans)

        for book in self.books:
            book["title"] = str(book.get("title", "")).strip()
            book["author"] = str(book.get("author", "")).strip()
            try:
                book["inventory"] = max(1, int(book.get("inventory", 1)))
            except (TypeError, ValueError):
                book["inventory"] = 1

        for student in self.students:
            student["name"] = str(student.get("name", "")).strip()

            grade = normalize_grade(student.get("grade", ""))
            section = str(student.get("section", "")).strip().upper()

            if grade is None:
                # стар формат: "class": "5а"
                old_class = str(student.get("class", "")).strip()
                digits = "".join(c for c in old_class if c.isdigit())
                letters = "".join(c for c in old_class if c.isalpha()).upper()
                grade = normalize_grade(digits) or "1"
                section = section or letters

            student["grade"] = grade
            student["section"] = section or "А"

            graduation = str(student.get("graduation_year", "")).strip()
            if not graduation.isdigit():
                graduation = str(default_graduation_year(grade))
            student["graduation_year"] = graduation
            student.pop("class", None)

        for loan in self.loans:
            for key in ("book_id", "student_id"):
                try:
                    loan[key] = int(loan.get(key))
                except (TypeError, ValueError):
                    loan[key] = -1
            loan["returned"] = bool(loan.get("returned", False))
            loan["return_date"] = str(loan.get("return_date", "") or "")
            loan["date"] = str(loan.get("date", "") or "")

    # ---------- търсене ----------

    @staticmethod
    def next_id(items):
        return max((item["id"] for item in items), default=0) + 1

    def find_book(self, book_id):
        for book in self.books:
            if book["id"] == book_id:
                return book
        return None

    def find_student(self, student_id):
        for student in self.students:
            if student["id"] == student_id:
                return student
        return None

    def find_loan(self, loan_id):
        for loan in self.loans:
            if loan["id"] == loan_id:
                return loan
        return None

    def active_loans_for_book(self, book_id):
        return [l for l in self.loans
                if l["book_id"] == book_id and not l["returned"]]

    def active_loans_for_student(self, student_id):
        return [l for l in self.loans
                if l["student_id"] == student_id and not l["returned"]]

    def active_counts_by_book(self):
        counts = {}
        for loan in self.loans:
            if not loan["returned"]:
                counts[loan["book_id"]] = counts.get(loan["book_id"], 0) + 1
        return counts

    def active_counts_by_student(self):
        counts = {}
        for loan in self.loans:
            if not loan["returned"]:
                counts[loan["student_id"]] = counts.get(loan["student_id"], 0) + 1
        return counts

    def available_copies(self, book):
        return max(0, book["inventory"] - len(self.active_loans_for_book(book["id"])))

    def loan_info(self, loan):
        book = self.find_book(loan["book_id"])
        student = self.find_student(loan["student_id"])
        title = book["title"] if book else "Изтрита книга"
        name = student["name"] if student else "Изтрит ученик"
        return book, student, title, name

    # ---------- операции ----------

    def lend(self, book_id, student_id):
        """Връща (заем, "") при успех или (None, съобщение за грешка)."""
        book = self.find_book(book_id)
        student = self.find_student(student_id)
        if not book or not student:
            return None, "Книгата или ученикът не е намерен."
        if self.available_copies(book) <= 0:
            return None, "Няма свободно копие от тази книга."
        for loan in self.active_loans_for_book(book_id):
            if loan["student_id"] == student_id:
                return None, "Този ученик вече има заета тази книга."

        now = datetime.now()
        loan = {
            "id": self.next_id(self.loans),
            "book_id": book_id,
            "student_id": student_id,
            "date": now.strftime(DATE_FMT),
            "due_date": (now + timedelta(days=LOAN_DAYS)).strftime(DAY_FMT),
            "returned": False,
            "return_date": "",
        }
        self.loans.append(loan)
        return loan, ""

    def give_back(self, loan):
        loan["returned"] = True
        loan["return_date"] = datetime.now().strftime(DATE_FMT)


# ----------------------------------------------------------------------------
# Графичен интерфейс
# ----------------------------------------------------------------------------

class App:
    def __init__(self, root, lib):
        self.root = root
        self.lib = lib

        root.title("📚 Училищна библиотека")
        root.geometry("1300x850")
        root.minsize(1050, 650)
        root.report_callback_exception = self.on_unhandled_error

        self.setup_style()
        self.build_header()
        self.build_statusbar()
        self.build_tabs()
        self.refresh_all()

        root.protocol("WM_DELETE_WINDOW", self.close)

    # ---------- общи ----------

    def setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", font=("Arial", 11))
        style.configure("Treeview", font=("Arial", 10), rowheight=28)
        style.configure("Treeview.Heading", font=("Arial", 10, "bold"))
        style.configure("TNotebook.Tab", font=("Arial", 11, "bold"), padding=(12, 7))

    def on_unhandled_error(self, exc_type, exc_value, exc_tb):
        logging.error("Необработена грешка", exc_info=(exc_type, exc_value, exc_tb))
        messagebox.showerror("Грешка", f"Възникна неочаквана грешка:\n\n{exc_value}")

    def commit(self):
        """Записва данните и опреснява всички таблици."""
        try:
            self.lib.save()
        except Exception as exc:  # noqa: BLE001
            logging.exception("Грешка при записване на данните.")
            messagebox.showerror("Грешка", f"Данните не могат да бъдат записани.\n\n{exc}")
        self.refresh_all()

    def close(self):
        try:
            self.lib.save()
        except Exception:  # noqa: BLE001
            logging.exception("Грешка при записване при затваряне.")
        logging.info("Програмата е затворена.")
        self.root.destroy()

    @staticmethod
    def selected_id(tree):
        selection = tree.selection()
        if not selection:
            return None
        try:
            return int(selection[0])
        except ValueError:
            return None

    def center(self, win, width=None, height=None):
        win.update_idletasks()
        width = width or win.winfo_reqwidth()
        height = height or win.winfo_reqheight()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
        win.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

    def make_modal(self, win):
        win.transient(self.root)
        try:
            win.wait_visibility()
            win.grab_set()
        except tk.TclError:
            pass

    def open_form(self, title, fields, button_text, on_submit):
        """Универсален диалог: fields = [(ключ, етикет, начална стойност)]."""
        win = tk.Toplevel(self.root)
        win.title(title)
        win.resizable(False, False)

        frame = ttk.Frame(win, padding=25)
        frame.pack(fill="both", expand=True)

        entries = {}
        for key, label, initial in fields:
            ttk.Label(frame, text=label).pack(anchor="w")
            entry = ttk.Entry(frame, font=("Arial", 12), width=42)
            entry.insert(0, initial)
            entry.pack(fill="x", pady=(5, 12))
            entries[key] = entry

        def submit(event=None):
            values = {key: entry.get().strip() for key, entry in entries.items()}
            if on_submit(values, win):
                win.destroy()

        ttk.Button(frame, text=button_text, command=submit).pack(
            fill="x", ipady=8, pady=(8, 0))

        win.bind("<Return>", submit)
        win.bind("<Escape>", lambda e: win.destroy())

        self.center(win, max(460, win.winfo_reqwidth()))
        self.make_modal(win)
        next(iter(entries.values())).focus_set()
        return win

    def popup_menu(self, event, entries):
        menu = tk.Menu(self.root, tearoff=0)
        for entry in entries:
            if entry is None:
                menu.add_separator()
            else:
                menu.add_command(label=entry[0], command=entry[1])
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def on_right_click(self, event, tree, menu_builder):
        row = tree.identify_row(event.y)
        if not row:
            return
        tree.selection_set(row)
        self.popup_menu(event, menu_builder(int(row)))

    def make_table(self, parent, columns):
        holder = ttk.Frame(parent)
        holder.pack(fill="both", expand=True)

        tree = ttk.Treeview(
            holder,
            columns=[c[0] for c in columns],
            show="headings",
            selectmode="browse",
        )
        for key, heading, width, anchor in columns:
            tree.heading(key, text=heading,
                         command=lambda k=key, t=tree: sort_tree(t, k, False))
            tree.column(key, width=width, anchor=anchor)

        scroll = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return tree

    def make_search_row(self, parent, label, var, buttons=()):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 10))
        ttk.Label(row, text=label).pack(side="left")
        entry = ttk.Entry(row, textvariable=var, font=("Arial", 11))
        entry.pack(side="left", fill="x", expand=True, padx=10)
        for text, command in buttons:
            ttk.Button(row, text=text, command=command).pack(side="left", padx=3)
        return entry

    # ---------- изграждане на интерфейса ----------

    def build_header(self):
        header = ttk.Frame(self.root, padding=(15, 12))
        header.pack(fill="x")

        ttk.Label(header, text="📚 УЧИЛИЩНА БИБЛИОТЕКА",
                  font=("Arial", 22, "bold")).pack(side="left")

        buttons = ttk.Frame(header)
        buttons.pack(side="right")
        for text, command, pad in [
            ("📖 ДАЙ КНИГА", self.give_book, 12),
            ("➕ Нова книга", self.add_book, 8),
            ("➕ Нов ученик", self.add_student, 8),
            ("📄 Експорт (CSV)", self.export_loans, 8),
        ]:
            ttk.Button(buttons, text=text, command=command).pack(
                side="left", padx=5, ipadx=pad, ipady=7)

    def build_statusbar(self):
        self.status_var = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status_var,
                  padding=(15, 6), anchor="w").pack(side="bottom", fill="x")

    def build_tabs(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        tabs = {}
        for key, text in [
            ("books", "📚 Книги"),
            ("students", "👨‍🎓 Ученици"),
            ("loans", "📖 Заети книги"),
            ("history", "🕘 История"),
            ("search", "🔎 Търсене"),
        ]:
            tabs[key] = ttk.Frame(notebook, padding=12)
            notebook.add(tabs[key], text=text)

        self.build_books_tab(tabs["books"])
        self.build_students_tab(tabs["students"])
        self.build_loans_tab(tabs["loans"])
        self.build_history_tab(tabs["history"])
        self.build_search_tab(tabs["search"])

    def build_books_tab(self, tab):
        self.book_search = tk.StringVar()
        entry = self.make_search_row(tab, "🔎 Търси книга:", self.book_search, [
            ("➕ Добави", self.add_book),
            ("✏️ Редактирай", self.edit_book),
            ("🗑️ Изтрий", self.remove_book),
        ])
        self.books_tree = self.make_table(tab, [
            ("id", "ID", 60, "center"),
            ("title", "Заглавие", 330, "w"),
            ("author", "Автор", 250, "w"),
            ("inventory", "Общо", 90, "center"),
            ("available", "Свободни", 100, "center"),
            ("loaned", "Заети", 90, "center"),
        ])
        self.book_search.trace_add("write", lambda *_: self.refresh_books())
        self.books_tree.bind("<Double-1>", lambda e: self.show_book_details())
        self.bind_context(self.books_tree, self.book_menu)
        entry.focus_set()

    def build_students_tab(self, tab):
        self.student_search = tk.StringVar()
        self.make_search_row(tab, "🔎 Търси ученик:", self.student_search, [
            ("➕ Добави", self.add_student),
            ("✏️ Редактирай", self.edit_student),
            ("⬆️ Нагоре", lambda: self.change_grade(+1)),
            ("⬇️ Надолу", lambda: self.change_grade(-1)),
            ("🎓 Нова учебна година", self.promote_all),
            ("🗑️ Изтрий", self.remove_student),
        ])
        self.students_tree = self.make_table(tab, [
            ("id", "ID", 60, "center"),
            ("name", "Име", 350, "w"),
            ("class", "Клас", 100, "center"),
            ("graduation", "Випуск", 120, "center"),
            ("loans", "Заети книги", 120, "center"),
        ])
        self.student_search.trace_add("write", lambda *_: self.refresh_students())
        self.students_tree.bind("<Double-1>", lambda e: self.show_student_details())
        self.bind_context(self.students_tree, self.student_menu)

    def build_loans_tab(self, tab):
        self.loan_search = tk.StringVar()
        self.make_search_row(tab, "🔎 Търси сред заетите книги:", self.loan_search, [
            ("↩️ Върни избраната", self.return_selected_loan),
        ])
        self.loans_tree = self.make_table(tab, [
            ("id", "Заем ID", 70, "center"),
            ("book_id", "Книга ID", 75, "center"),
            ("book", "Книга", 240, "w"),
            ("student_id", "Ученик ID", 85, "center"),
            ("student", "Ученик", 210, "w"),
            ("class", "Клас", 70, "center"),
            ("graduation", "Випуск", 80, "center"),
            ("date", "Дадена на", 130, "center"),
            ("due", "Срок", 100, "center"),
            ("status", "Статус", 100, "center"),
        ])
        self.loans_tree.tag_configure("overdue", foreground="#b00020")
        self.loan_search.trace_add("write", lambda *_: self.refresh_loans())
        self.loans_tree.bind("<Double-1>", lambda e: self.show_loan_details())
        self.bind_context(self.loans_tree, self.loan_menu)

    def build_history_tab(self, tab):
        self.history_search = tk.StringVar()
        self.make_search_row(tab, "🔎 Търси в историята:", self.history_search)
        self.history_tree = self.make_table(tab, [
            ("id", "Заем ID", 70, "center"),
            ("book", "Книга", 280, "w"),
            ("student", "Ученик", 240, "w"),
            ("class", "Клас", 70, "center"),
            ("date", "Дадена на", 140, "center"),
            ("return_date", "Върната на", 140, "center"),
            ("status", "Статус", 100, "center"),
        ])
        self.history_tree.tag_configure("overdue", foreground="#b00020")
        self.history_search.trace_add("write", lambda *_: self.refresh_history())
        self.history_tree.bind("<Double-1>", lambda e: self.show_loan_details(self.history_tree))

    def build_search_tab(self, tab):
        self.general_search = tk.StringVar()
        self.make_search_row(tab, "🔎 Общо търсене:", self.general_search)
        self.general_tree = self.make_table(tab, [
            ("type", "Тип", 100, "center"),
            ("id", "ID", 80, "center"),
            ("name", "Име / Заглавие", 350, "w"),
            ("info", "Допълнителна информация", 500, "w"),
        ])
        self.general_search.trace_add("write", lambda *_: self.refresh_general())
        self.general_tree.bind("<Double-1>", self.general_double_click)

    def bind_context(self, tree, menu_builder):
        handler = lambda e: self.on_right_click(e, tree, menu_builder)
        tree.bind("<Button-3>", handler)
        if sys.platform == "darwin":
            tree.bind("<Button-2>", handler)
            tree.bind("<Control-Button-1>", handler)

    # ---------- опресняване на таблиците ----------

    def refresh_all(self):
        self.refresh_books()
        self.refresh_students()
        self.refresh_loans()
        self.refresh_history()
        self.refresh_general()
        self.refresh_status()

    @staticmethod
    def clear(tree):
        tree.delete(*tree.get_children())

    def refresh_books(self):
        query = self.book_search.get().strip().lower()
        self.clear(self.books_tree)
        counts = self.lib.active_counts_by_book()

        for book in self.lib.books:
            text = f"{book['id']} {book['title']} {book['author']}".lower()
            if query and query not in text:
                continue
            active = counts.get(book["id"], 0)
            self.books_tree.insert("", "end", iid=str(book["id"]), values=(
                book["id"], book["title"], book["author"] or "—",
                book["inventory"], max(0, book["inventory"] - active), active,
            ))

    def refresh_students(self):
        query = self.student_search.get().strip().lower()
        self.clear(self.students_tree)
        counts = self.lib.active_counts_by_student()

        for student in self.lib.students:
            text = (f"{student['id']} {student['name']} {student_class(student)} "
                    f"{student['graduation_year']}").lower()
            if query and query not in text:
                continue
            self.students_tree.insert("", "end", iid=str(student["id"]), values=(
                student["id"], student["name"], student_class(student),
                student["graduation_year"], counts.get(student["id"], 0),
            ))

    @staticmethod
    def loan_status(loan):
        if loan["returned"]:
            return "Върната"
        return "Просрочена" if is_overdue(loan) else "Заета"

    def refresh_loans(self):
        query = self.loan_search.get().strip().lower()
        self.clear(self.loans_tree)

        for loan in self.lib.loans:
            if loan["returned"]:
                continue
            _, student, title, name = self.lib.loan_info(loan)
            klass = student_class(student)
            graduation = student["graduation_year"] if student else "—"
            text = (f"{loan['id']} {loan['book_id']} {title} {loan['student_id']} "
                    f"{name} {klass} {graduation} {loan['date']}").lower()
            if query and query not in text:
                continue
            tags = ("overdue",) if is_overdue(loan) else ()
            self.loans_tree.insert("", "end", iid=str(loan["id"]), tags=tags, values=(
                loan["id"], loan["book_id"], title, loan["student_id"], name,
                klass, graduation, loan["date"], loan_due(loan) or "—",
                self.loan_status(loan),
            ))

    def refresh_history(self):
        query = self.history_search.get().strip().lower()
        self.clear(self.history_tree)

        for loan in reversed(self.lib.loans):
            _, student, title, name = self.lib.loan_info(loan)
            klass = student_class(student)
            text = (f"{loan['id']} {title} {name} {klass} {loan['date']} "
                    f"{loan['return_date']}").lower()
            if query and query not in text:
                continue
            tags = ("overdue",) if is_overdue(loan) else ()
            self.history_tree.insert("", "end", iid=str(loan["id"]), tags=tags, values=(
                loan["id"], title, name, klass, loan["date"],
                loan["return_date"] or "—", self.loan_status(loan),
            ))

    def refresh_general(self):
        query = self.general_search.get().strip().lower()
        self.clear(self.general_tree)
        if not query:
            return

        for book in self.lib.books:
            text = f"{book['id']} {book['title']} {book['author']}".lower()
            if query in text:
                self.general_tree.insert("", "end", iid=f"book:{book['id']}", values=(
                    "Книга", book["id"], book["title"], book["author"] or "—"))

        for student in self.lib.students:
            klass = student_class(student)
            text = (f"{student['id']} {student['name']} {klass} "
                    f"{student['graduation_year']}").lower()
            if query in text:
                self.general_tree.insert("", "end", iid=f"student:{student['id']}", values=(
                    "Ученик", student["id"], student["name"],
                    f"{klass} | Випуск {student['graduation_year']}"))

        for loan in self.lib.loans:
            if loan["returned"]:
                continue
            _, student, title, name = self.lib.loan_info(loan)
            klass = student_class(student)
            text = f"{loan['id']} {title} {name} {klass} {loan['date']}".lower()
            if query in text:
                self.general_tree.insert("", "end", iid=f"loan:{loan['id']}", values=(
                    "Заем", loan["id"], title, f"{name} | {klass}"))

    def refresh_status(self):
        total_copies = sum(b["inventory"] for b in self.lib.books)
        active = [l for l in self.lib.loans if not l["returned"]]
        overdue = sum(1 for l in active if is_overdue(l))
        self.status_var.set(
            f"Заглавия: {len(self.lib.books)}   |   Копия: {total_copies} "
            f"(свободни: {total_copies - len(active)})   |   "
            f"Ученици: {len(self.lib.students)}   |   "
            f"Заети книги: {len(active)}   |   Просрочени: {overdue}"
        )

    def general_double_click(self, event=None):
        selection = self.general_tree.selection()
        if not selection:
            return
        kind, _, raw_id = selection[0].partition(":")
        item_id = int(raw_id)
        if kind == "book":
            self.show_book_details(item_id)
        elif kind == "student":
            self.show_student_details(item_id)
        elif kind == "loan":
            self.show_loan_details(loan_id=item_id)

    # ---------- книги ----------

    def add_book(self):
        self.open_form("➕ Нова книга", [
            ("title", "Заглавие:", ""),
            ("author", "Автор:", ""),
            ("inventory", "Брой налични копия:", "1"),
        ], "💾 Запази книгата", lambda v, w: self.save_book(v, w))

    def edit_book(self, book_id=None):
        book_id = book_id or self.selected_id(self.books_tree)
        if book_id is None:
            messagebox.showwarning("Внимание", "Избери книга.")
            return
        book = self.lib.find_book(book_id)
        if not book:
            messagebox.showerror("Грешка", "Книгата не е намерена.")
            return
        self.open_form("✏️ Редактиране на книга", [
            ("title", "Заглавие:", book["title"]),
            ("author", "Автор:", book["author"]),
            ("inventory", "Брой налични копия:", str(book["inventory"])),
        ], "💾 Запази промените", lambda v, w: self.save_book(v, w, book))

    def save_book(self, values, win, book=None):
        title = values["title"]
        author = values["author"]

        if not title:
            messagebox.showwarning("Внимание", "Въведи заглавие.", parent=win)
            return False
        try:
            inventory = int(values["inventory"])
        except ValueError:
            messagebox.showerror("Грешка", "Броят копия трябва да е число.", parent=win)
            return False
        if inventory < 1:
            messagebox.showwarning("Внимание", "Броят копия трябва да е поне 1.", parent=win)
            return False

        if book is None:
            book = {"id": self.lib.next_id(self.lib.books), "title": title,
                    "author": author, "inventory": inventory}
            self.lib.books.append(book)
            logging.info("Добавена книга: %s", title)
        else:
            active = len(self.lib.active_loans_for_book(book["id"]))
            if inventory < active:
                messagebox.showwarning(
                    "Внимание",
                    f"Тази книга има {active} активни заема.\n"
                    f"Броят копия не може да е по-малък от {active}.",
                    parent=win)
                return False
            book.update(title=title, author=author, inventory=inventory)
            logging.info("Редактирана книга с ID %s.", book["id"])

        self.commit()
        return True

    def remove_book(self, book_id=None):
        book_id = book_id or self.selected_id(self.books_tree)
        if book_id is None:
            messagebox.showwarning("Внимание", "Избери книга.")
            return
        book = self.lib.find_book(book_id)
        if not book:
            messagebox.showerror("Грешка", "Книгата не е намерена.")
            return
        if self.lib.active_loans_for_book(book_id):
            messagebox.showwarning(
                "Не може да се изтрие",
                "Книгата не може да бъде изтрита, защото има активен заем.")
            return
        if not messagebox.askyesno(
                "Потвърждение", f"Сигурен ли си, че искаш да изтриеш:\n\n„{book['title']}“?"):
            return
        self.lib.books.remove(book)
        logging.info("Изтрита книга с ID %s.", book_id)
        self.commit()

    def show_book_details(self, book_id=None):
        book_id = book_id or self.selected_id(self.books_tree)
        book = self.lib.find_book(book_id) if book_id is not None else None
        if not book:
            messagebox.showerror("Грешка", "Книгата не е намерена.")
            return
        active = len(self.lib.active_loans_for_book(book_id))
        messagebox.showinfo("📖 Детайли за книгата", (
            f"ID: {book['id']}\n"
            f"Заглавие: {book['title']}\n"
            f"Автор: {book['author'] or '—'}\n"
            f"Общо копия: {book['inventory']}\n"
            f"Свободни копия: {self.lib.available_copies(book)}\n"
            f"Заети копия: {active}"
        ))

    def book_menu(self, book_id):
        entries = [
            ("ℹ️ Детайли", lambda: self.show_book_details(book_id)),
            ("✏️ Редактирай", lambda: self.edit_book(book_id)),
        ]
        if self.lib.active_loans_for_book(book_id):
            entries.append(("↩️ Върни книга", lambda: self.return_for_book(book_id)))
        entries += [None, ("🗑️ Изтрий", lambda: self.remove_book(book_id))]
        return entries

    # ---------- ученици ----------

    def add_student(self):
        self.open_form("➕ Нов ученик", [
            ("name", "Име и фамилия:", ""),
            ("grade", "Клас (1-12):", ""),
            ("section", "Паралелка (напр. А):", ""),
            ("graduation", "Випуск (оставете празно за автоматично):", ""),
        ], "💾 Запази ученика", lambda v, w: self.save_student(v, w))

    def edit_student(self, student_id=None):
        student_id = student_id or self.selected_id(self.students_tree)
        if student_id is None:
            messagebox.showwarning("Внимание", "Избери ученик.")
            return
        student = self.lib.find_student(student_id)
        if not student:
            messagebox.showerror("Грешка", "Ученикът не е намерен.")
            return
        self.open_form("✏️ Редактиране на ученик", [
            ("name", "Име и фамилия:", student["name"]),
            ("grade", "Клас (1-12):", student["grade"]),
            ("section", "Паралелка (напр. А):", student["section"]),
            ("graduation", "Випуск:", student["graduation_year"]),
        ], "💾 Запази промените", lambda v, w: self.save_student(v, w, student))

    def save_student(self, values, win, student=None):
        name = values["name"]
        grade = normalize_grade(values["grade"])
        section = values["section"].upper()
        graduation = values["graduation"]

        if not name:
            messagebox.showwarning("Внимание", "Въведи име.", parent=win)
            return False
        if not grade:
            messagebox.showwarning("Внимание", "Класът трябва да е число от 1 до 12.", parent=win)
            return False
        if not section:
            messagebox.showwarning("Внимание", "Въведи паралелка.", parent=win)
            return False
        if not graduation:
            graduation = str(default_graduation_year(grade))
        elif not (graduation.isdigit() and len(graduation) == 4
                  and 2000 <= int(graduation) <= 2100):
            messagebox.showwarning(
                "Внимание", "Випускът трябва да е година (например 2035).", parent=win)
            return False

        if student is None:
            student = {"id": self.lib.next_id(self.lib.students)}
            self.lib.students.append(student)
            logging.info("Добавен ученик: %s", name)
        else:
            logging.info("Редактиран ученик с ID %s.", student["id"])

        student.update(name=name, grade=grade, section=section, graduation_year=graduation)
        self.commit()
        return True

    def change_grade(self, step, student_id=None):
        student_id = student_id or self.selected_id(self.students_tree)
        if student_id is None:
            messagebox.showwarning("Внимание", "Избери ученик.")
            return
        student = self.lib.find_student(student_id)
        if not student:
            messagebox.showerror("Грешка", "Ученикът не е намерен.")
            return
        grade = int(student["grade"])
        if step > 0 and grade >= 12:
            messagebox.showinfo("Информация", "Ученикът вече е в 12 клас.")
            return
        if step < 0 and grade <= 1:
            messagebox.showinfo("Информация", "Ученикът вече е в 1 клас.")
            return
        student["grade"] = str(grade + step)
        logging.info("Ученик %s - нов клас %s.", student_id, student["grade"])
        self.commit()

    def promote_all(self):
        candidates = [s for s in self.lib.students if int(s["grade"]) < 12]
        if not candidates:
            messagebox.showinfo("Информация", "Няма ученици, които да бъдат преместени.")
            return
        if not messagebox.askyesno(
                "Нова учебна година",
                f"{len(candidates)} ученици (до 11 клас) ще бъдат преместени в "
                f"следващия клас.\nУчениците от 12 клас остават без промяна.\n\n"
                f"Продължаване?"):
            return
        for student in candidates:
            student["grade"] = str(int(student["grade"]) + 1)
        logging.info("Нова учебна година: преместени %s ученици.", len(candidates))
        self.commit()

    def remove_student(self, student_id=None):
        student_id = student_id or self.selected_id(self.students_tree)
        if student_id is None:
            messagebox.showwarning("Внимание", "Избери ученик.")
            return
        student = self.lib.find_student(student_id)
        if not student:
            messagebox.showerror("Грешка", "Ученикът не е намерен.")
            return
        if self.lib.active_loans_for_student(student_id):
            messagebox.showwarning(
                "Не може да се изтрие",
                "Ученикът не може да бъде изтрит, защото има активни заеми.")
            return
        if not messagebox.askyesno(
                "Потвърждение", f"Сигурен ли си, че искаш да изтриеш:\n\n{student['name']}?"):
            return
        self.lib.students.remove(student)
        logging.info("Изтрит ученик с ID %s.", student_id)
        self.commit()

    def show_student_details(self, student_id=None):
        student_id = student_id or self.selected_id(self.students_tree)
        student = self.lib.find_student(student_id) if student_id is not None else None
        if not student:
            messagebox.showerror("Грешка", "Ученикът не е намерен.")
            return
        active = self.lib.active_loans_for_student(student_id)
        lines = [
            f"ID: {student['id']}",
            f"Име: {student['name']}",
            f"Клас: {student_class(student)}",
            f"Випуск: {student['graduation_year']}",
            f"Активни книги: {len(active)}",
        ]
        for loan in active:
            _, _, title, _ = self.lib.loan_info(loan)
            mark = "  (просрочена!)" if is_overdue(loan) else ""
            lines.append(f"   • {title} - срок {loan_due(loan) or '—'}{mark}")
        messagebox.showinfo("👨‍🎓 Детайли за ученика", "\n".join(lines))

    def student_menu(self, student_id):
        return [
            ("ℹ️ Детайли", lambda: self.show_student_details(student_id)),
            ("✏️ Редактирай", lambda: self.edit_student(student_id)),
            ("⬆️ По-горен клас", lambda: self.change_grade(+1, student_id)),
            ("⬇️ По-долен клас", lambda: self.change_grade(-1, student_id)),
            None,
            ("🗑️ Изтрий", lambda: self.remove_student(student_id)),
        ]

    # ---------- заеми ----------

    def give_book(self):
        win = tk.Toplevel(self.root)
        win.title("📖 Даване на книга")
        win.minsize(850, 550)
        win.geometry("1050x650")
        win.transient(self.root)

        main = ttk.Frame(win, padding=15)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="📖 ДАВАНЕ НА КНИГА",
                  font=("Arial", 18, "bold")).pack(pady=(0, 15))

        columns = ttk.Frame(main)
        columns.pack(fill="both", expand=True)

        books_frame = ttk.LabelFrame(columns, text="📚 Свободни книги", padding=10)
        books_frame.pack(side="left", fill="both", expand=True, padx=(0, 7))
        students_frame = ttk.LabelFrame(columns, text="👨‍🎓 Ученици", padding=10)
        students_frame.pack(side="left", fill="both", expand=True, padx=(7, 0))

        book_query = tk.StringVar()
        student_query = tk.StringVar()

        ttk.Label(books_frame, text="🔎 Търси книга:").pack(anchor="w")
        book_entry = ttk.Entry(books_frame, textvariable=book_query, font=("Arial", 11))
        book_entry.pack(fill="x", pady=(5, 10))
        ttk.Label(students_frame, text="🔎 Търси ученик:").pack(anchor="w")
        ttk.Entry(students_frame, textvariable=student_query,
                  font=("Arial", 11)).pack(fill="x", pady=(5, 10))

        book_tree = self.make_table(books_frame, [
            ("id", "ID", 55, "center"),
            ("title", "Заглавие", 230, "w"),
            ("author", "Автор", 170, "w"),
            ("available", "Свободни", 80, "center"),
        ])
        student_tree = self.make_table(students_frame, [
            ("id", "ID", 55, "center"),
            ("name", "Име", 230, "w"),
            ("class", "Клас", 70, "center"),
            ("graduation", "Випуск", 90, "center"),
        ])

        def fill_books(*_):
            query = book_query.get().strip().lower()
            self.clear(book_tree)
            for book in self.lib.books:
                available = self.lib.available_copies(book)
                if available <= 0:
                    continue
                text = f"{book['id']} {book['title']} {book['author']}".lower()
                if query and query not in text:
                    continue
                book_tree.insert("", "end", iid=str(book["id"]), values=(
                    book["id"], book["title"], book["author"] or "—", available))

        def fill_students(*_):
            query = student_query.get().strip().lower()
            self.clear(student_tree)
            for student in self.lib.students:
                text = (f"{student['id']} {student['name']} {student_class(student)} "
                        f"{student['graduation_year']}").lower()
                if query and query not in text:
                    continue
                student_tree.insert("", "end", iid=str(student["id"]), values=(
                    student["id"], student["name"], student_class(student),
                    student["graduation_year"]))

        def lend_selected(event=None):
            book_id = self.selected_id(book_tree)
            student_id = self.selected_id(student_tree)
            if book_id is None:
                messagebox.showwarning("Внимание", "Избери книга.", parent=win)
                return
            if student_id is None:
                messagebox.showwarning("Внимание", "Избери ученик.", parent=win)
                return
            loan, error = self.lib.lend(book_id, student_id)
            if loan is None:
                messagebox.showwarning("Не може да се даде", error, parent=win)
                fill_books()
                return
            logging.info("Дадена книга ID %s на ученик ID %s.", book_id, student_id)
            self.commit()
            messagebox.showinfo(
                "Готово", f"Книгата е дадена.\nСрок за връщане: {loan['due_date']}",
                parent=self.root)
            win.destroy()

        book_query.trace_add("write", fill_books)
        student_query.trace_add("write", fill_students)

        ttk.Button(main, text="📖 ДАЙ КНИГАТА", command=lend_selected).pack(
            fill="x", pady=(15, 0), ipady=12)
        win.bind("<Escape>", lambda e: win.destroy())

        fill_books()
        fill_students()
        book_entry.focus_set()

    def return_selected_loan(self):
        loan_id = self.selected_id(self.loans_tree)
        if loan_id is None:
            messagebox.showwarning("Внимание", "Избери заем.")
            return
        self.return_loan(loan_id)

    def return_for_book(self, book_id):
        active = self.lib.active_loans_for_book(book_id)
        if not active:
            messagebox.showinfo("Информация", "Тази книга няма активни заеми.")
            return
        if len(active) == 1:
            self.return_loan(active[0]["id"])
            return

        win = tk.Toplevel(self.root)
        win.title("↩️ Избери заем")
        win.geometry("700x400")
        frame = ttk.Frame(win, padding=15)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Тази книга има няколко активни заема.\n"
                              "Избери кой заем да върнеш:").pack(pady=(0, 10))

        tree = self.make_table(frame, [
            ("id", "ID", 60, "center"),
            ("student", "Ученик", 250, "w"),
            ("class", "Клас", 80, "center"),
            ("date", "Дата", 150, "center"),
        ])
        for loan in active:
            student = self.lib.find_student(loan["student_id"])
            tree.insert("", "end", iid=str(loan["id"]), values=(
                loan["id"], student["name"] if student else "Неизвестен",
                student_class(student), loan["date"]))

        def choose(event=None):
            loan_id = self.selected_id(tree)
            if loan_id is None:
                messagebox.showwarning("Внимание", "Избери заем.", parent=win)
                return
            win.destroy()
            self.return_loan(loan_id)

        tree.bind("<Double-1>", choose)
        ttk.Button(frame, text="↩️ Върни избрания заем", command=choose).pack(
            fill="x", pady=(10, 0), ipady=7)
        self.make_modal(win)

    def return_loan(self, loan_id):
        loan = self.lib.find_loan(loan_id)
        if not loan:
            messagebox.showerror("Грешка", "Заемът не е намерен.")
            return
        if loan["returned"]:
            messagebox.showinfo("Информация", "Тази книга вече е върната.")
            return
        _, _, title, name = self.lib.loan_info(loan)
        if not messagebox.askyesno(
                "Потвърждение",
                f"Да бъде ли отбелязана като върната книгата:\n\n„{title}“\n"
                f"Ученик: {name}?"):
            return
        self.lib.give_back(loan)
        logging.info("Върната книга по заем ID %s.", loan_id)
        self.commit()

    def show_loan_details(self, tree=None, loan_id=None):
        if loan_id is None:
            loan_id = self.selected_id(tree or self.loans_tree)
        loan = self.lib.find_loan(loan_id) if loan_id is not None else None
        if not loan:
            messagebox.showerror("Грешка", "Заемът не е намерен.")
            return
        _, student, title, name = self.lib.loan_info(loan)
        messagebox.showinfo("📖 Детайли за заема", (
            f"Заем ID: {loan['id']}\n"
            f"Книга ID: {loan['book_id']}\n"
            f"Книга: {title}\n"
            f"Ученик ID: {loan['student_id']}\n"
            f"Ученик: {name}\n"
            f"Клас: {student_class(student)}\n"
            f"Випуск: {student['graduation_year'] if student else '—'}\n"
            f"Дата на даване: {loan['date'] or '—'}\n"
            f"Срок за връщане: {loan_due(loan) or '—'}\n"
            f"Статус: {self.loan_status(loan)}\n"
            f"Дата на връщане: {loan['return_date'] or '—'}"
        ))

    def loan_menu(self, loan_id):
        return [
            ("ℹ️ Детайли", lambda: self.show_loan_details(loan_id=loan_id)),
            ("↩️ Върни книгата", lambda: self.return_loan(loan_id)),
        ]

    # ---------- експорт ----------

    def export_loans(self):
        path = filedialog.asksaveasfilename(
            title="Експорт на заемите",
            defaultextension=".csv",
            initialfile=f"zaemi_{datetime.now().strftime(DAY_FMT)}.csv",
            filetypes=[("CSV файлове", "*.csv")],
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file, delimiter=";")
                writer.writerow(["Заем ID", "Книга", "Автор", "Ученик", "Клас",
                                 "Випуск", "Дадена на", "Срок", "Върната на", "Статус"])
                for loan in self.lib.loans:
                    book, student, title, name = self.lib.loan_info(loan)
                    writer.writerow([
                        loan["id"], title, book["author"] if book else "", name,
                        student_class(student),
                        student["graduation_year"] if student else "",
                        loan["date"], loan_due(loan), loan["return_date"],
                        self.loan_status(loan),
                    ])
            messagebox.showinfo("Готово", f"Файлът е записан:\n{path}")
        except OSError as exc:
            logging.exception("Грешка при експорт.")
            messagebox.showerror("Грешка", f"Файлът не може да бъде записан.\n\n{exc}")


# ----------------------------------------------------------------------------
# Старт
# ----------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")],
    )

    root = tk.Tk()
    lib = Library(DATA_FILE)
    error = lib.load()
    App(root, lib)

    if error:
        messagebox.showerror(
            "Грешка",
            "Файлът с данните не може да бъде зареден.\n\n"
            f"{error}\n\nПовреденият файл е запазен като library_data.json.broken.",
            parent=root,
        )
    root.mainloop()


if __name__ == "__main__":
    main()