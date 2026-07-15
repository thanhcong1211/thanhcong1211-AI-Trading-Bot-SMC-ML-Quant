'use client';

import { useEffect, useRef } from 'react';
import { motion, useAnimation } from 'framer-motion';

interface FlashValueProps {
  value: number;
  className?: string;
  children: React.ReactNode;
}

const FLASH_UP = 'rgba(0, 255, 65, 0.35)';
const FLASH_DOWN = 'rgba(255, 51, 51, 0.35)';
const FLASH_OFF = 'rgba(0, 0, 0, 0)';

/** Wraps a numeric display value and flashes green/red when it changes. */
export function FlashValue({ value, className, children }: FlashValueProps) {
  const controls = useAnimation();
  const previousValue = useRef(value);
  const mounted = useRef(false);

  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      previousValue.current = value;
      return;
    }
    if (value === previousValue.current) return;

    const isUp = value > previousValue.current;
    previousValue.current = value;

    controls.set({ backgroundColor: isUp ? FLASH_UP : FLASH_DOWN });
    controls.start({ backgroundColor: FLASH_OFF, transition: { duration: 0.9, ease: 'easeOut' } });
  }, [value, controls]);

  return (
    <motion.span
      initial={{ backgroundColor: FLASH_OFF }}
      animate={controls}
      className={`rounded px-1 transition-colors ${className ?? ''}`}
    >
      {children}
    </motion.span>
  );
}
