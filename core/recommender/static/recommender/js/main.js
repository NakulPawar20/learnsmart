/**
 * LearnSmart - Interactive landing page JavaScript
 */

document.addEventListener('DOMContentLoaded', function () {
  // Mobile menu toggle
  const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
  const nav = document.querySelector('.nav');

  if (mobileMenuBtn && nav) {
    mobileMenuBtn.addEventListener('click', function () {
      mobileMenuBtn.classList.toggle('active');
      nav.classList.toggle('open');
      document.body.style.overflow = nav.classList.contains('open') ? 'hidden' : '';
    });
  }

  // Close mobile menu when clicking a nav link
  const navLinks = document.querySelectorAll('.nav__link, .btn');
  navLinks.forEach(function (link) {
    link.addEventListener('click', function () {
      if (nav && nav.classList.contains('open')) {
        mobileMenuBtn.classList.remove('active');
        nav.classList.remove('open');
        document.body.style.overflow = '';
      }
    });
  });

  // Smooth scroll for anchor links (enhance native scroll-behavior)
  document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
    anchor.addEventListener('click', function (e) {
      const href = this.getAttribute('href');
      if (href === '#') return;
      
      const target = document.querySelector(href);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }
    });
  });

  // Header scroll effect - add shadow when scrolled
  const header = document.querySelector('.header');
  if (header) {
    window.addEventListener('scroll', function () {
      if (window.scrollY > 50) {
        header.style.boxShadow = '0 4px 20px rgba(0, 0, 0, 0.15)';
      } else {
        header.style.boxShadow = '0 2px 12px rgba(0, 0, 0, 0.1)';
      }
    });
  }

  // Roadmap Search - Client-side filtering
  const roadmapSearchInput = document.querySelector('.roadmap-search__input');
  if (roadmapSearchInput) {
    // Store original roadmap cards
    const roadmapGrid = document.querySelector('.roadmaps__grid');
    const roadmapCards = Array.from(roadmapGrid.querySelectorAll('.roadmap-card:not(.roadmap-card--custom)'));
    const customCard = roadmapGrid.querySelector('.roadmap-card--custom');

    // Add real-time search filtering
    roadmapSearchInput.addEventListener('input', function () {
      const searchTerm = this.value.toLowerCase().trim();

      if (searchTerm === '') {
        // Show all cards
        roadmapCards.forEach(card => {
          card.style.display = '';
          card.style.opacity = '1';
        });
      } else {
        // Filter cards based on search term
        let visibleCount = 0;
        roadmapCards.forEach(card => {
          const title = card.querySelector('h3').textContent.toLowerCase();
          const description = card.querySelector('p').textContent.toLowerCase();
          
          if (title.includes(searchTerm) || description.includes(searchTerm)) {
            card.style.display = '';
            card.style.opacity = '1';
            visibleCount++;
          } else {
            card.style.display = 'none';
            card.style.opacity = '0';
          }
        });

        // Show message if no results
        if (visibleCount === 0) {
          // Try to find or create an empty state message
          let emptyMessage = roadmapGrid.querySelector('.roadmap-search-empty');
          if (!emptyMessage) {
            emptyMessage = document.createElement('div');
            emptyMessage.className = 'roadmap-search-empty';
            emptyMessage.innerHTML = '<p>No roadmaps found for "' + escapeHtml(this.value) + '". Try a different search term.</p>';
            roadmapGrid.appendChild(emptyMessage);
          } else {
            emptyMessage.innerHTML = '<p>No roadmaps found for "' + escapeHtml(this.value) + '". Try a different search term.</p>';
            emptyMessage.style.display = '';
          }
        } else {
          const emptyMessage = roadmapGrid.querySelector('.roadmap-search-empty');
          if (emptyMessage) {
            emptyMessage.style.display = 'none';
          }
        }
      }
    });
  }

  // Utility function to escape HTML
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Feature cards - hover effects handled by CSS
});
