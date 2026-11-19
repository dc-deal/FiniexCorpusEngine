/**
 * Browser interfaces jsdom does not implement, supplied so the components that use them can be tested at all (Y1.a: taken
 * from the FiniexViewer's test setup with the facet bar). They stand in for MISSING APIs and never replace behaviour under
 * test: a stub that answered differently from a browser would make the suite agree with itself rather than with reality.
 * Reka UI's floating layer and the overflow row measure their elements, which is why ResizeObserver is needed; its menus
 * capture the pointer.
 */
class ResizeObserverStub implements ResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

if (!('ResizeObserver' in globalThis)) {
  globalThis.ResizeObserver = ResizeObserverStub
}

if (typeof Element !== 'undefined' && !Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = (): boolean => false
  Element.prototype.setPointerCapture = (): void => {}
  Element.prototype.releasePointerCapture = (): void => {}
}
