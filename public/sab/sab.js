(() => {
    const secret = document.getElementById('secret-chamber');
    const mirrorBox = document.querySelector('[data-mirror]');
    const riddleInput = document.getElementById('riddle-input');
    const unlockButtons = Array.from(document.querySelectorAll('[data-action="unlock"]'));

    const isUnlocked = () => localStorage.getItem('sab_riddle_unlocked') === 'true';

    const setLockState = (locked) => {
        unlockButtons.forEach((button) => {
            if (button instanceof HTMLButtonElement) {
                button.disabled = locked;
            }
            button.classList.toggle('locked', locked);
            button.setAttribute('aria-disabled', locked ? 'true' : 'false');
        });
    };

    const openSecret = () => {
        if (!secret) return;
        secret.classList.add('show');
        secret.setAttribute('aria-hidden', 'false');
    };

    const closeSecret = () => {
        if (!secret) return;
        secret.classList.remove('show');
        secret.setAttribute('aria-hidden', 'true');
    };

    const attemptUnlock = () => {
        const answer = riddleInput ? riddleInput.value.trim() : '';
        if (!answer) {
            if (riddleInput) {
                riddleInput.classList.add('shake');
                setTimeout(() => riddleInput.classList.remove('shake'), 350);
            }
            return false;
        }
        localStorage.setItem('sab_riddle_unlocked', 'true');
        setLockState(false);
        return true;
    };

    setLockState(!isUnlocked());

    document.addEventListener('click', (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) return;
        const action = target.getAttribute('data-action');
        if (action === 'unlock') {
            if (isUnlocked()) {
                openSecret();
            }
        }
        if (action === 'answer') {
            if (attemptUnlock()) {
                openSecret();
            }
        }
        if (action === 'close-secret') {
            closeSecret();
        }
        if (action === 'mirror' && mirrorBox) {
            mirrorBox.classList.toggle('mirrored');
        }
    });

    if (riddleInput) {
        riddleInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                if (attemptUnlock()) {
                    openSecret();
                }
            }
        });
    }

    if (mirrorBox) {
        mirrorBox.addEventListener('mouseenter', () => mirrorBox.classList.add('mirrored'));
        mirrorBox.addEventListener('mouseleave', () => mirrorBox.classList.remove('mirrored'));
    }

    // Hidden joke for those who open the console.
    console.log('SAB: The chamber opens after you write, not before.');
})();
