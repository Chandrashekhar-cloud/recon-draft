/**
 * Recon Draft - Vanilla Client-Side Interactions
 * Offline only: Zero CDNs, Zero External Libraries
 */

(function () {
  'use strict';

  // 1. Theme Management (Saved in localStorage, Projector Ready)
  const THEME_KEY = 'recon_theme';

  function initTheme() {
    const savedTheme = localStorage.getItem(THEME_KEY);
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initialTheme = savedTheme ? savedTheme : (prefersDark ? 'dark' : 'light');

    document.documentElement.setAttribute('data-theme', initialTheme);
    updateThemeToggleIcons(initialTheme);
  }

  function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';

    document.documentElement.setAttribute('data-theme', nextTheme);
    localStorage.setItem(THEME_KEY, nextTheme);
    updateThemeToggleIcons(nextTheme);

    showToast({
      title: 'Theme Switched',
      message: `Active appearance: ${nextTheme === 'dark' ? 'Dark (Projector)' : 'Light'}`,
      type: 'info',
      duration: 2500
    });
  }

  function updateThemeToggleIcons(theme) {
    const sunIcons = document.querySelectorAll('.theme-icon-sun');
    const moonIcons = document.querySelectorAll('.theme-icon-moon');

    if (theme === 'dark') {
      sunIcons.forEach(el => el.style.display = 'inline-block');
      moonIcons.forEach(el => el.style.display = 'none');
    } else {
      sunIcons.forEach(el => el.style.display = 'none');
      moonIcons.forEach(el => el.style.display = 'inline-block');
    }
  }

  // 2. Tab Navigation
  function initTabs() {
    document.addEventListener('click', function (e) {
      const tabBtn = e.target.closest('.tab-btn');
      if (!tabBtn) return;

      const targetId = tabBtn.getAttribute('data-tab');
      if (!targetId) return;

      const navContainer = tabBtn.closest('.tabs-nav');
      if (!navContainer) return;

      const parentWrapper = navContainer.parentElement;

      // Update button active state
      navContainer.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
      tabBtn.classList.add('active');

      // Update pane active state
      parentWrapper.querySelectorAll('.tab-pane').forEach(pane => {
        if (pane.id === targetId) {
          pane.classList.add('active');
        } else {
          pane.classList.remove('active');
        }
      });
    });
  }

  // 3. Modal Manager
  function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.classList.remove('open');
    document.body.style.overflow = '';
  }

  function initModals() {
    // Backdrop & close button click
    document.addEventListener('click', function (e) {
      if (e.target.classList.contains('modal-backdrop')) {
        closeModal(e.target.id);
      }
      const closeBtn = e.target.closest('[data-modal-close]');
      if (closeBtn) {
        const modal = closeBtn.closest('.modal-backdrop');
        if (modal) closeModal(modal.id);
      }
      const openBtn = e.target.closest('[data-modal-open]');
      if (openBtn) {
        const targetId = openBtn.getAttribute('data-modal-open');
        if (targetId) openModal(targetId);
      }
    });

    // Close on Escape
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        const openModalEl = document.querySelector('.modal-backdrop.open');
        if (openModalEl) closeModal(openModalEl.id);
      }
    });
  }

  // 4. Toast Notifications
  function getToastContainer() {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    return container;
  }

  function showToast({ title, message, type = 'info', duration = 4000 }) {
    const container = getToastContainer();
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    let iconSvg = '';
    if (type === 'success') {
      iconSvg = '<svg class="toast-icon" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>';
    } else if (type === 'warning') {
      iconSvg = '<svg class="toast-icon" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>';
    } else if (type === 'danger') {
      iconSvg = '<svg class="toast-icon" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/></svg>';
    } else {
      iconSvg = '<svg class="toast-icon" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/></svg>';
    }

    toast.innerHTML = `
      ${iconSvg}
      <div class="toast-content">
        <div class="toast-title">${title}</div>
        ${message ? `<div class="toast-message">${message}</div>` : ''}
      </div>
      <button class="toast-close" aria-label="Close">&times;</button>
    `;

    toast.querySelector('.toast-close').addEventListener('click', () => {
      dismissToast(toast);
    });

    container.appendChild(toast);

    if (duration > 0) {
      setTimeout(() => dismissToast(toast), duration);
    }
  }

  function dismissToast(toast) {
    if (!toast || toast.classList.contains('toast-hiding')) return;
    toast.classList.add('toast-hiding');
    setTimeout(() => {
      if (toast.parentElement) toast.remove();
    }, 220);
  }

  // 5. Code Block Copying
  function initCodeCopy() {
    document.addEventListener('click', function (e) {
      const copyBtn = e.target.closest('[data-copy-target]');
      if (!copyBtn) return;

      const targetId = copyBtn.getAttribute('data-copy-target');
      const targetEl = document.getElementById(targetId);
      if (!targetEl) return;

      const textToCopy = targetEl.innerText || targetEl.textContent;
      navigator.clipboard.writeText(textToCopy).then(() => {
        const origHtml = copyBtn.innerHTML;
        copyBtn.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>
          Copied!
        `;
        copyBtn.style.borderColor = 'var(--color-success)';
        copyBtn.style.color = 'var(--color-success)';

        setTimeout(() => {
          copyBtn.innerHTML = origHtml;
          copyBtn.style.borderColor = '';
          copyBtn.style.color = '';
        }, 2000);
      }).catch(err => {
        console.error('Clipboard copy failed:', err);
      });
    });
  }

  // 6. Mobile Sidebar Toggle
  function initSidebarToggle() {
    const toggleBtn = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('app-sidebar');

    if (toggleBtn && sidebar) {
      toggleBtn.addEventListener('click', function () {
        sidebar.classList.toggle('open');
      });

      // Close when clicking outside on mobile
      document.addEventListener('click', function (e) {
        if (window.innerWidth <= 900) {
          if (!sidebar.contains(e.target) && !toggleBtn.contains(e.target) && sidebar.classList.contains('open')) {
            sidebar.classList.remove('open');
          }
        }
      });
    }
  }

  // Export functions to window for onclick handlers
  window.ReconApp = {
    toggleTheme: toggleTheme,
    openModal: openModal,
    closeModal: closeModal,
    showToast: showToast
  };

  // Run on DOM loaded
  document.addEventListener('DOMContentLoaded', function () {
    initTheme();
    initTabs();
    initModals();
    initCodeCopy();
    initSidebarToggle();

    // Attach theme toggle button
    const themeBtn = document.getElementById('theme-toggle-btn');
    if (themeBtn) {
      themeBtn.addEventListener('click', toggleTheme);
    }
  });
})();
