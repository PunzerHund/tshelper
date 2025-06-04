import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_from_directory

files_bp = Blueprint('files', __name__, url_prefix='/files')

def get_user_materials_dir():
    return os.path.join('/opt/mentors', session['user']['name'], 'materials')

@files_bp.route('/', methods=['GET', 'POST'])
def index():
    user_folder = get_user_materials_dir()
    os.makedirs(user_folder, exist_ok=True)

    # Загрузка одного или нескольких файлов
    if request.method == 'POST':
        uploaded_files = request.files.getlist('file')
        saved = False
        for uploaded in uploaded_files:
            if uploaded and uploaded.filename:
                # сохраняем без secure_filename, чтобы сохранить кириллицу
                filename = os.path.basename(uploaded.filename)
                uploaded.save(os.path.join(user_folder, filename))
                saved = True
        if saved:
            flash('Файл(ы) загружен(ы).', 'success')
        else:
            flash('Нет файлов для загрузки.', 'warning')
        return redirect(url_for('files.index'))

    files = []
    for fname in sorted(os.listdir(user_folder)):
        fpath = os.path.join(user_folder, fname)
        if os.path.isfile(fpath):
            files.append(fname)

    return render_template('files.html', files=files)

@files_bp.route('/edit/<filename>', methods=['GET', 'POST'])
def edit_file(filename):
    user_folder = get_user_materials_dir()
    filepath = os.path.join(user_folder, filename)
    if not os.path.abspath(filepath).startswith(os.path.abspath(user_folder)):
        flash('Нельзя редактировать этот файл.', 'danger')
        return redirect(url_for('files.index'))

    if request.method == 'POST':
        new_filename = request.form.get('new_filename', filename).strip()
        # сохраняем новое имя как basename, чтобы не удалять кириллицу
        new_filepath = os.path.join(user_folder, os.path.basename(new_filename))
        content = request.form.get('content', '')

        if new_filename != filename:
            if os.path.exists(new_filepath):
                flash('Файл с таким именем уже существует.', 'danger')
                return redirect(url_for('files.edit_file', filename=filename))
            os.rename(filepath, new_filepath)
            filepath = new_filepath
            filename = new_filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        flash('Файл сохранён.', 'success')
        return redirect(url_for('files.index'))

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    return render_template('edit_file.html', filename=filename, content=content)

@files_bp.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    user_folder = get_user_materials_dir()
    filepath = os.path.join(user_folder, filename)
    if not os.path.abspath(filepath).startswith(os.path.abspath(user_folder)):
        flash('Нельзя удалить этот файл.', 'danger')
        return redirect(url_for('files.index'))

    try:
        os.remove(filepath)
        flash('Файл удалён.', 'success')
    except Exception as e:
        flash(f'Ошибка удаления: {e}', 'danger')
    return redirect(url_for('files.index'))

@files_bp.route('/download/<filename>')
def download_file(filename):
    user_folder = get_user_materials_dir()
    return send_from_directory(user_folder, filename, as_attachment=True)