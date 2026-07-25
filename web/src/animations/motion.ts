import { motion, type Variants } from "framer-motion";
export const pageTransition: Variants = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0, transition: { duration: .24, ease: [.2, .8, .2, 1] } }, exit: { opacity: 0, y: -8, transition: { duration: .16 } } };
export const fadeIn: Variants = { hidden: { opacity: 0 }, visible: { opacity: 1, transition: { duration: .24 } } };
export const slideUp: Variants = { hidden: { opacity: 0, y: 12 }, visible: { opacity: 1, y: 0, transition: { duration: .24 } } };
export const scaleIn: Variants = { hidden: { opacity: 0, scale: .96 }, visible: { opacity: 1, scale: 1, transition: { duration: .24 } } };
export const staggerContainer: Variants = { hidden: {}, visible: { transition: { staggerChildren: .06 } } };
export const loadingPulse: Variants = { initial: { opacity: .5 }, animate: { opacity: [ .5, 1, .5 ], transition: { duration: 1.4, repeat: Infinity } } };
export { motion };
