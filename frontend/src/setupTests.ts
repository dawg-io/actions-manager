// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

// Mock axios for all tests
vi.mock('axios');

// jsdom has no layout engine, so scrollIntoView is simply absent. Components
// that scroll a newly revealed panel into view would throw on mount.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {};
}

// Mock HTMLDialogElement methods for jsdom
// jsdom doesn't fully support the native dialog element yet
if (typeof HTMLDialogElement === 'undefined') {
  (globalThis as any).HTMLDialogElement = class HTMLDialogElement extends HTMLElement {
    open = false;
    returnValue = '';
    
    showModal() {
      this.open = true;
    }
    
    show() {
      this.open = true;
    }
    
    close(returnValue?: string) {
      this.open = false;
      if (returnValue !== undefined) {
        this.returnValue = returnValue;
      }
      // Dispatch close event
      const closeEvent = new Event('close', { bubbles: false, cancelable: false });
      this.dispatchEvent(closeEvent);
    }
  };
} else {
  // Polyfill for jsdom's incomplete dialog implementation
  const originalShowModal = HTMLDialogElement.prototype.showModal;
  const originalShow = HTMLDialogElement.prototype.show;
  const originalClose = HTMLDialogElement.prototype.close;
  
  HTMLDialogElement.prototype.showModal = function(this: HTMLDialogElement) {
    if (originalShowModal) {
      try {
        originalShowModal.call(this);
      } catch (e) {
        // Fallback if showModal is not fully implemented
        console.warn('showModal fallback:', e);
        this.setAttribute('open', '');
        (this as any).open = true;
      }
    } else {
      this.setAttribute('open', '');
      (this as any).open = true;
    }
  };
  
  HTMLDialogElement.prototype.show = function(this: HTMLDialogElement) {
    if (originalShow) {
      try {
        originalShow.call(this);
      } catch (e) {
        console.warn('show fallback:', e);
        this.setAttribute('open', '');
        (this as any).open = true;
      }
    } else {
      this.setAttribute('open', '');
      (this as any).open = true;
    }
  };
  
  HTMLDialogElement.prototype.close = function(this: HTMLDialogElement, returnValue?: string) {
    if (originalClose) {
      try {
        originalClose.call(this, returnValue);
      } catch (e) {
        console.warn('close fallback:', e);
        this.removeAttribute('open');
        (this as any).open = false;
        if (returnValue !== undefined) {
          (this as any).returnValue = returnValue;
        }
        const closeEvent = new Event('close', { bubbles: false, cancelable: false });
        this.dispatchEvent(closeEvent);
      }
    } else {
      this.removeAttribute('open');
      (this as any).open = false;
      if (returnValue !== undefined) {
        (this as any).returnValue = returnValue;
      }
      const closeEvent = new Event('close', { bubbles: false, cancelable: false });
      this.dispatchEvent(closeEvent);
    }
  };
}
